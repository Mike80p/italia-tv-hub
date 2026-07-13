from pathlib import Path
from src.core.application import Application
def main(): return Application(Path(__file__).resolve().parents[1]).run()
if __name__=='__main__': raise SystemExit(main())
