# Bottlenose

This is an implementation of the
[DELPH-IN RESTful API](http://moin.delph-in.net/ErgApi)
using ACE and pyDelphin as the backend.

## Deprecation Notice

This project is now deprecated will no longer be developed.
Users are advised to
migrate to the PyDelphin's built-in
[web server](https://pydelphin.readthedocs.io/en/latest/api/delphin.web.server.html),
or otherwise use PyDelphin
[v0.9.2](https://pypi.org/project/PyDelphin/0.9.2/).

## Quick Start

Configure your grammars and ACE in [config.py](config.py), make
sure the [requirements](#requirements) are satisfied and importable
(e.g. by
[setting PYTHONPATH](https://docs.python.org/3/using/cmdline.html#envvar-PYTHONPATH)),
and run:

    python3 bottlenose.py

Send requests to the server (assuming this is run locally at
http://127.0.0.1:8080)

    curl -v http://127.0.0.1:8080/erg/parse?mrs=json\&input=Abrams%20barks.
    [...]
    < HTTP/1.0 200 OK
    [...]
    < Content-Type: application/json
    {"pedges": "42", "results": [{"result-id": 0, "mrs": {"top": "h0", ...

If you want a client to read the responses from the server, try
[pyDelphin's REST interface](https://github.com/delph-in/pydelphin/blob/master/delphin/interfaces/rest.py).

## Requirements

- [Python 3.3+](http://python.org)
- [ACE](http://sweaglesw.org/linguistics/ace/)
- [PyDelphin](https://github.com/delph-in/pydelphin) (last supported version: [v0.9.2](https://pypi.org/project/PyDelphin/0.9.2/))
- [Flask](http://flask.pocoo.org/)
- [Flask-CORS](https://flask-cors.corydolphin.com/)

## Disclaimer

Bottlenose currently only implements a subset of the functions defined
by the [API](http://moin.delph-in.net/ErgApi), but it also provides
DMRS output and it works with non-ERG grammars as well.

