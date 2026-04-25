import inspect
import json

def log(message, level='INFO'):
    frame = inspect.currentframe().f_back
    line_number = frame.f_lineno
    emojis = {'INFO':'ℹ️','WARNING':'⚠️','ERROR':'❌','SUCCESS':'✅'}
    print(f"{emojis.get(level,'ℹ️')} [{level}] (Linha {line_number}): {message}")

def dumps(obj, **kwargs):
    return json.dumps(obj, default=str, **kwargs)
