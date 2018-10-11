
import os
import re
import json
from functools import wraps

from flask import Flask, request, abort, jsonify
from flask_cors import CORS

from delphin.interfaces import rest, ace
from delphin.mrs import simplemrs, eds, penman, Mrs, Dmrs
from delphin import derivation
from delphin import tokens
from delphin.extra import latex


# Basic init

app = Flask(__name__)
app.config.from_object('config')
CORS(app)

ACE_ENV = dict(os.environ)
ACE_ENV['LANG'] = 'en_US.UTF-8'  # change as necessary
ACE_OPTIONS = {
    'executable': app.config['ACE'].get('executable', 'ace'),
    'cmdargs': app.config['ACE'].get('cmdargs', []),
    'env': ACE_ENV
}

GRAMMARS = {}
for gramdata in app.config['GRAMMARS']:
    GRAMMARS[gramdata['key'].lower()] = gramdata


# Config interface

def _get_grammar(grmkey):
    grmkey = grmkey.lower()  # normalize key
    if grmkey not in GRAMMARS:
        abort(404, 'No grammar is specified for "%s".' % grmkey)
    grm = GRAMMARS.get(grmkey)
    if not os.path.exists(grm.get('path')):
        abort(503, 'The grammar could not be found.')
    return grm


## Parameter validation

def _param(cast=None, choices=None, default=None):
    def validate(val):
        if val is None:
            return default
        if choices is not None and val not in choices:
            raise ValueError("'{}' is not a valid value ({})"
                             .format(val, ', '.join(choices)))
        if cast is not None:
            val = cast(val)
        return val
    return validate


def _make_re(s):
    try:
        return re.compile(s)
    except re.error:
        raise ValueError('Invalid regular expression: {}'.format(s))


def _get_params(query, param_spec):
    params = {}
    errors = []
    for key, get_param in param_spec.items():
        try:
            params[key] = get_param(query.get(key))
        except ValueError as ex:
            errors.append('  {}: {}'.format(key, str(ex)))
    if errors:
        abort(400, '\n'.join(['Invalid parameters:'] + errors))
    return params


# Parsing

PARSE_PARAMS = {
    'analyses':     _param(cast=int, default=100),
    'results':      _param(cast=int, default=1),
    # 'time':         _param(),
    # 'roots':        _param(),
    'generics':     _param(choices=['all', 'null'], default='all'),
    'tokens':       _param(choices=['json', 'yy', 'null'], default='null'),
    'derivation':   _param(choices=['json', 'udf', 'null'], default='null'),
    'mrs':          _param(choices=['json', 'simple', 'latex', 'null'],
                          default='null'),
    'eds':          _param(choices=['json', 'native', 'penman', 'amr',
                                   'latex', 'null'],
                          default='null'),
    'dmrs':         _param(choices=['json', 'penman', 'latex', 'null'],
                          default='null'),
    'properties':   _param(choices=['json', 'null'], default='json'),
    'filter':       _param(cast=_make_re)
}


@app.route('/<grmkey>/parse')
def parse(grmkey):
    grm = _get_grammar(grmkey)
    params = _get_params(request.args, PARSE_PARAMS)
    inp = request.args.get('input', '')
    opts = dict(ACE_OPTIONS)
    opts['cmdargs'] = opts.get('cmdargs', []) + ['-n', str(params['results'])]
    ace_response = ace.parse(
        grm['path'],
        inp,
        **opts
    )
    return jsonify(_parse_repsonse(inp, ace_response, params))


def _parse_repsonse(inp, ace_response, params):
    properties = True if params.get('properties') == 'json' else False

    tcpu = ace_response.get('tcpu')
    pedges = ace_response.get('pedges')
    readings = ace_response.get('readings')
    if readings is None:
        readings = len(ace_response.get('results', []))

    result_data = []
    for i, res in enumerate(ace_response.results()):
        mrs, udf = res['mrs'], res['derivation']
        xmrs = simplemrs.loads_one(mrs)
        d = {'result-id': i}

        if params.get('derivation') == 'udf':
            d['derivation'] = udf
        elif params.get('derivation') == 'json':
            d['derivation'] = _udf_to_dict(udf, params)

        if params.get('mrs') == 'simple':
            d['mrs'] = mrs
        elif params.get('mrs') == 'json':
            d['mrs'] = Mrs.to_dict(xmrs, properties=properties)
        elif params.get('mrs') == 'latex':
            abort(501, "The 'latex' format for MRS is not yet implemented.")

        if params.get('eds') == 'native':
            d['eds'] = eds.dumps(xmrs, single=True)
        elif params.get('eds') == 'json':
            d['eds'] = eds.Eds.from_xmrs(xmrs).to_dict(properties=properties)
        elif params.get('eds') in ('amr', 'penman'):
            d['eds'] = penman.dumps([xmrs], model=eds.Eds)
        elif params.get('eds') == 'latex':
            abort(501, "The 'latex' format for EDS is not yet implemented.")

        if params.get('dmrs') == 'json':
            d['dmrs'] = Dmrs.to_dict(xmrs, properties=properties)
        elif params.get('dmrs') == 'penman':
            d['dmrs'] = penman.dumps([xmrs], model=Dmrs)
        elif params.get('dmrs') == 'latex':
            d['dmrs'] = latex.dmrs_tikz_dependency(xmrs)

        result_data.append(d)

    data = {
        'input': inp,
        'readings': readings,
        'results': result_data
    }
    if tcpu is not None: data['tcpu'] = tcpu
    if pedges is not None: data['pedges'] = pedges
    if params.get('tokens'):
        t1 = ace_response.tokens('initial')
        t2 = ace_response.tokens('internal')
        if params['tokens'] == 'json':
            data['tokens'] = {
                'initial': t1.to_list(),
                'internal': t2.to_list()
            }
        elif params['tokens'] == 'yy':
            data['tokens'] = {
                'initial': str(t1),
                'internal': str(t2)
            }

    return data


def _udf_to_dict(udf, params):
    d = derivation.Derivation.from_string(udf)
    return d.to_dict(fields=['id', 'entity', 'score', 'form', 'tokens'])


# Generation

GENERATE_PARAMS = {
    'results':      _param(cast=int, default=1),
    # 'time':         _param(),
    # 'roots':        _param(),
    'derivation':   _param(choices=['json', 'udf', 'null'], default='null'),
}


@app.route('/<grmkey>/generate')
def generate(grmkey):
    grm = _get_grammar(grmkey)
    params = _get_params(request.args, GENERATE_PARAMS)
    inp = request.args.get('input', '')
    opts = dict(ACE_OPTIONS)
    opts['cmdargs'] = opts.get('cmdargs', []) + ['-n', str(params['results'])]
    # decode simplemrs just to validate input
    try:
        xmrs = simplemrs.loads_one(inp)
    except Exception:
        abort(500, 'invalid input MRS')
    ace_response = ace.generate(
        grm['path'],
        simplemrs.dumps_one(xmrs),
        **opts
    )
    return jsonify(_generation_response(inp, ace_response, params))


def _generation_response(inp, ace_response, params):
    tcpu = ace_response.get('tcpu')
    pedges = ace_response.get('pedges')
    readings = ace_response.get('readings')
    if readings is None:
        readings = len(ace_response.get('results', []))
    result_data = []
    for i, res in enumerate(ace_response.results()):
        udf = res['derivation']
        d = {'result-id': i,
             'surface': res['surface']}
        if params.get('derivation') == 'udf':
            d['derivation'] = udf
        elif params.get('derivation') == 'json':
            d['derivation'] = _udf_to_dict(udf, params)
        result_data.append(d)
    data = {
        'input': inp,
        'readings': readings,
        'results': result_data
    }
    if tcpu is not None: data['tcpu'] = tcpu
    if pedges is not None: data['pedges'] = pedges
    return data


if __name__ == '__main__':
    app.run()

