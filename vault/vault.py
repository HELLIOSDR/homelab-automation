#!/usr/bin/env python3
"""
VAULT — baza projektów Hellios
Zapisuje klocki (raporty, projekty, snapshoty) z CRC32, podpisem CC i timestampem.
Uruchamiaj: python3 vault.py --save <plik> [--tag <tag>]
             python3 vault.py --list
             python3 vault.py --verify <id>
             python3 vault.py --snapshot  # zapisuje stan workspace co godzinę
"""
import sqlite3, hashlib, zlib, json, sys, os, argparse
from datetime import datetime

DB = "/home/lenovo/workspace/vault.db"
WORKSPACE = "/home/lenovo/workspace"
AUTHOR = "Claude Code (CC) — Sonnet 4.6 — dla Helliosa"

def init_db():
    con = sqlite3.connect(DB)
    con.execute("""
        CREATE TABLE IF NOT EXISTS vault (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            crc32 TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            author TEXT NOT NULL,
            tags TEXT,
            created_at TEXT NOT NULL,
            size_bytes INTEGER
        )
    """)
    con.commit()
    return con

def crc32_str(s):
    return format(zlib.crc32(s.encode()) & 0xFFFFFFFF, '08X')

def sha256_str(s):
    return hashlib.sha256(s.encode()).hexdigest()[:16]

def save_entry(con, title, content, tags=""):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    crc = crc32_str(content)
    sha = sha256_str(content)
    size = len(content.encode())
    con.execute(
        "INSERT INTO vault (title, content, crc32, sha256, author, tags, created_at, size_bytes) VALUES (?,?,?,?,?,?,?,?)",
        (title, content, crc, sha, AUTHOR, tags, now, size)
    )
    con.commit()
    row = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    print(f"[VAULT] #{row} zapisany | CRC32: {crc} | SHA: {sha} | {now}")
    print(f"        Tytuł: {title} | {size} bajtów")
    return row, crc

def list_entries(con, limit=20):
    rows = con.execute(
        "SELECT id, title, crc32, sha256, created_at, size_bytes, tags FROM vault ORDER BY id DESC LIMIT ?",
        (limit,)
    ).fetchall()
    print(f"\n{'ID':>4} | {'CRC32':>8} | {'SHA':>16} | {'Data':>19} | {'KB':>5} | Tytuł")
    print("-" * 85)
    for r in rows:
        kb = (r[5] or 0) // 1024
        print(f"{r[0]:>4} | {r[2]:>8} | {r[3]:>16} | {r[4]:>19} | {kb:>4}K | {r[1]}")

def verify_entry(con, entry_id):
    row = con.execute("SELECT * FROM vault WHERE id=?", (entry_id,)).fetchone()
    if not row:
        print(f"[VAULT] Brak wpisu #{entry_id}")
        return
    id_, title, content, crc, sha, author, tags, created, size = row
    crc_now = crc32_str(content)
    sha_now = sha256_str(content)
    ok_crc = crc_now == crc
    ok_sha = sha_now == sha
    status = "OK" if (ok_crc and ok_sha) else "ZMIENIONY!"
    print(f"\n[VAULT] Wpis #{id_}: {title}")
    print(f"  Autor:   {author}")
    print(f"  Data:    {created}")
    print(f"  CRC32:   {crc} → {crc_now} {'✓' if ok_crc else '✗'}")
    print(f"  SHA256:  {sha} → {sha_now} {'✓' if ok_sha else '✗'}")
    print(f"  Status:  {status}")

def snapshot(con):
    """Zapisuje snapshot stanu workspace — lista plików i rozmiary"""
    files = []
    for root, dirs, fnames in os.walk(WORKSPACE):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in fnames:
            p = os.path.join(root, f)
            try:
                s = os.path.getsize(p)
                files.append({"f": p.replace(WORKSPACE+"/",""), "s": s})
            except:
                pass
    content = json.dumps({"files": files, "count": len(files)}, ensure_ascii=False)
    title = f"SNAPSHOT workspace {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    return save_entry(con, title, content, tags="snapshot,auto")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--save", metavar="FILE", help="Zapisz plik do vault")
    parser.add_argument("--tag", default="", help="Tagi (przecinkami)")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--verify", type=int, metavar="ID")
    parser.add_argument("--snapshot", action="store_true")
    args = parser.parse_args()

    con = init_db()

    if args.save:
        with open(args.save, "r", errors="replace") as fh:
            content = fh.read()
        title = os.path.basename(args.save)
        save_entry(con, title, content, tags=args.tag)
    elif args.list:
        list_entries(con)
    elif args.verify:
        verify_entry(con, args.verify)
    elif args.snapshot:
        snapshot(con)
    else:
        parser.print_help()
