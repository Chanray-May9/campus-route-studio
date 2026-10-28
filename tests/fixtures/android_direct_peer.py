"""Protocol peer for transport tests, not an Android permission emulator."""
import json
from pathlib import Path
import sys

mode, scenario, record = sys.argv[1:]
events = []

def event(value):
    events.append(value)
    Path(record).write_text(json.dumps(events), encoding='utf-8')

def reply(**packet):
    print('CRS1 ' + json.dumps(packet), flush=True)

print('test peer boot log', flush=True)
event({'argument': mode})
if scenario == 'denied':
    reply(id=0, ok=False, error='permission denied', closed=True, cleanupError='')
elif mode == 'probe':
    reply(id=0, ok=True, probe=True, sdk=35, locationEnabled=True)
else:
    reply(id=0, ok=True, ready=True, providers=['network'] if scenario == 'no-gps' else ['gps', 'network'])
    for line in sys.stdin:
        request = json.loads(line)
        event(request)
        if request['action'] == 'stop':
            reply(id=request['id'], ok=True, closed=True)
            break
        if scenario == 'disconnect':
            sys.exit(3)
        reply(id=request['id'] + (1 if scenario == 'bad-sequence' else 0), ok=True, sent=len(events)-1)
    event({'cleaned': True})
