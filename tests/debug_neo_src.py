import inspect
import neo.rawio.winwcprawio
from neo.rawio.winwcprawio import WinWcpRawIO

print("Location:", neo.rawio.winwcprawio.__file__)
try:
    src = inspect.getsource(WinWcpRawIO._parse_header)
    print("Source of _parse_header:")
    print(src)
except Exception as e:
    print(f"Could not get source: {e}")
