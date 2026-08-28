import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.downloader import baixar_fnde_municipio_completo

if __name__ == "__main__":
    r = baixar_fnde_municipio_completo("2902104", "Araci", "BA", 2025)
    print(r)
