import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "appfnde.db"


def conectar():
    con = sqlite3.connect(DB)
    con.execute("""
        CREATE TABLE IF NOT EXISTS downloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
            ibge TEXT,
            municipio TEXT,
            uf TEXT,
            ano INTEGER,
            cnpj TEXT,
            fonte TEXT,
            endpoint TEXT,
            arquivo TEXT,
            status TEXT,
            http_status INTEGER,
            tamanho_bytes INTEGER,
            detalhe TEXT
        )
    """)
    con.commit()
    return con


def registrar(**dados):
    con = conectar()
    cols = ["ibge","municipio","uf","ano","cnpj","fonte","endpoint","arquivo","status","http_status","tamanho_bytes","detalhe"]
    vals = [dados.get(c) for c in cols]
    con.execute(f"INSERT INTO downloads ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})", vals)
    con.commit()
    con.close()


def listar(limite=200):
    con = conectar()
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT * FROM downloads ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
    con.close()
    return [dict(r) for r in rows]
