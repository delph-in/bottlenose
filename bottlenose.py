
import os
import re
import json
from functools import wraps

from bottle import (
    Bottle,
    abort,
    default_app,
    request,
    response,
    route,
    run,
)

from delphin.interfaces import rest, ace
from delphin.mrs import simplemrs, eds, penman, Mrs, Dmrs
from delphin import derivation
from delphin import tokens
from delphin.extra import latex


# Basic init

app = default_app()

# maybe constrain this to known origins to avoid excessive requests
cors_origin = '*'

# this can be set from app.wsgi if the server path is known
cwd = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(cwd, 'config.json')) as fp:
    app.config.load_dict(json.load(fp))

ace_env = dict(os.environ)
ace_env['LANG'] = 'en_US.UTF-8'  # change as necessary
ace_options = {
    'executable': app.config.get('bottlenose.ace.executable', 'ace'),
    'cmdargs': app.config.get('bottlenose.ace.cmdargs', []),
    'env': ace_env
}

grammars = {}
for gramdata in app.config['bottlenose.grammars']:
    grammars[gramdata['key'].lower()] = gramdata


# Config interface

def get_grammar(grmkey):
    grmkey = grmkey.lower()  # normalize key
    if grmkey not in grammars:
        abort(404, 'No grammar is specified for "%s".' % grmkey)
    grm = grammars.get(grmkey)
    if not os.path.exists(grm.get('path')):
        abort(503, 'The grammar could not be found.')
    return grm


## Parameter validation

def param(cast=None, choices=None, default=None):
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


def make_re(s):
    try:
        return re.compile(s)
    except re.error:
        raise ValueError('Invalid regular expression: {}'.format(s))


def get_params(query, param_spec):
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


## CORS support

# thanks: https://gist.github.com/richard-flosi/3789163
@app.hook('after_request')
def enable_cors():
    response.headers['Access-Control-Allow-Origin'] = cors_origin

    # if preflight requests (e.g. OPTIONS method) are allowed
    # response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    # response.headers['Access-Control-Allow-Headers'] = \
    #     'Origin, Accept, Content-type, X-Requested-With, X-CSRF-Token'
    
    # if custom headers are used:
    # response.headers['Access-Control-Expose-Headers'] = 'X-Custom-Header'

## JSON-P support

# thanks: http://flask.pocoo.org/snippets/79/
def jsonp(func):
    """Wraps JSONified output for JSONP requests."""
    @wraps(func)
    def decorated_function(*args, **kwargs):
        callback = request.query.get('callback', False)
        if callback:
            if not app.config['bottlenose.allow_jsonp']:
                abort(400, 'JSON-P callbacks are disabled for this request.')
            # maybe check if Accept is application/json
            data = func(*args, **kwargs)
            body = '{}({})'.format(str(callback), json.dumps(data))
            response.content_type = 'application/javascript'
            return body
        else:
            return func(*args, **kwargs)
    return decorated_function


# Parsing

parse_params = {
    'analyses':     param(cast=int, default=100),
    'results':      param(cast=int, default=1),
    # 'time':         param(),
    # 'roots':        param(),
    'generics':     param(choices=['all', 'null'], default='all'),
    'tokens':       param(choices=['json', 'yy', 'null'], default='null'),
    'derivation':   param(choices=['json', 'udf', 'null'], default='null'),
    'mrs':          param(choices=['json', 'simple', 'latex', 'null'],
                          default='null'),
    'eds':          param(choices=['json', 'native', 'amr', 'latex', 'null'],
                          default='null'),
    'dmrs':         param(choices=['json', 'penman', 'latex', 'null'],
                          default='null'),
    'properties':   param(choices=['json', 'null'], default='json'),
    'filter':       param(cast=make_re)
}


@route('/<grmkey>/parse')
@jsonp
def parse(grmkey):
    grm = get_grammar(grmkey)
    query = request.query.decode()
    params = get_params(query, parse_params)
    inp = query['input']
    opts = dict(ace_options)
    opts['cmdargs'] = opts.get('cmdargs', []) + ['-n', str(params['results'])]
    ace_response = ace.parse(
        grm['path'],
        inp,
        **opts
    )
    return parse_response(inp, ace_response, params)

def parse_response(inp, ace_response, params):
    properties = True if params.get('properties') == 'json' else False
    tcpu, pedges = _get_parse_info(ace_response.get('NOTES', []))
    result_data = []
    for i, res in enumerate(ace_response.results()):
        mrs, udf = res['mrs'], res['derivation']
        xmrs = simplemrs.loads_one(mrs)
        d = {'result-id': i}

        if params.get('derivation') == 'udf':
            d['derivation'] = udf
        elif params.get('derivation') == 'json':
            d['derivation'] = udf_to_dict(udf, params)

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
        'readings': len(ace_response.get('RESULTS', [])),
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

def udf_to_dict(udf, params):
    d = derivation.Derivation.from_string(udf)
    return d.to_dict(fields=['id', 'entity', 'score', 'form', 'tokens'])

def _get_parse_info(notes):
    tcpu, pedges = None, None
    for note in notes:
        m = re.search(r'added \d+ \/ (?P<edges>\d+) edges to chart', note)
        if m:
            pedges = m.group('edges')
        # time is not available until after the last parse...
        # m = re.search(r'parsed.*, time (?P<time>\d+\.\d+)s', note)
        # if m:
        #     tcpu = m.group('time')
    return tcpu, pedges




# Generation

# generate_params = {
#     'analyses':     param(cast=int, default=100),
#     'results':      param(cast=int, default=1),
#     # 'time':         param(),
#     # 'roots':        param(),
#     'generics':     param(choices=['all', 'null'], default='all'),
#     'derivation':   param(choices=['json', 'udf', 'null'], default='null'),
#     'mrs':          param(choices=['json', 'simple', 'latex', 'null'],
#                           default='null'),
#     'eds':          param(choices=['json', 'native', 'latex', 'null'],
#                           default='null'),
#     'dmrs':         param(choices=['json', 'latex', 'null'],
#                           default='null'),
#     'properties':   param(choices=['json', 'null'], default='json'),
#     'filter':       param(cast=make_re)
# }

# @route('/<grmkey>/generate')
# def generate(grmkey):
#     grm = get_grammar(grmkey)
#     query = request.query.decode()
#     params = get_params(query, generate_params)
#     inp = query['input']
#     print(inp)
#     xmrs = simplemrs.loads_one(inp)
#     result = ace.generate(
#         grm, simplemrs.dumps_one(xmrs), cmdargs=['-n', str(params['results'])]
#     )
#     return result

if __name__ == '__main__':
    run()

