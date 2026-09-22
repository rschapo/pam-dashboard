"""
organizar_car_baixado.py — põe os ZIPs do SICAR no lugar que o pipeline espera.

O download do SICAR é manual (CAPTCHA por arquivo), então o operador baixa tudo
para uma pasta só. Este script varre essa pasta, identifica de que UF e de que
camada é cada ZIP e extrai para data/raw/car/<uf>/<camada>/.

A camada é identificada pelos shapefiles de dentro do ZIP, não pelo nome do
arquivo: o nome muda conforme o navegador resolve duplicatas ("(1)", "_2"), e o
conteúdo não mente. A UF vem do nome do ZIP ou de --uf.

Uso:
  python organizar_car_baixado.py --origem ~/Downloads
  python organizar_car_baixado.py --origem ~/Downloads --uf MT   # força a UF
  python organizar_car_baixado.py --status                        # só o que falta

Não apaga nada da origem: move para <origem>/_organizados/ após extrair, para
que uma segunda execução não reprocesse o mesmo arquivo.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import unicodedata
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import RAW_DIR, UFS, UF_NAMES  # noqa: E402

# Trecho que identifica a camada no nome dos shapefiles de dentro do ZIP.
# A ordem importa: "area_consolidada" antes de "area" evita casar errado.
ASSINATURAS = [
    ("area_consolidada",  ["area_consolidada", "areaconsolidada"]),
    ("vegetacao_nativa",  ["vegetacao_nativa", "vegetacaonativa", "remanescente"]),
    ("reserva_legal",     ["reserva_legal", "reservalegal"]),
    ("uso_restrito",      ["uso_restrito", "usorestrito"]),
    ("app",               ["apps", "app_", "area_preservacao", "preservacao_permanente"]),
    ("imoveis",           ["area_imovel", "areaimovel", "perimetro"]),
]
CAMADAS_AMBIENTAIS = ["area_consolidada", "vegetacao_nativa", "reserva_legal", "app", "uso_restrito"]


def detectar_camada(zf: zipfile.ZipFile) -> str | None:
    nomes = " ".join(n.lower() for n in zf.namelist())
    for camada, marcas in ASSINATURAS:
        if any(m in nomes for m in marcas):
            return camada
    return None


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn").upper()


def detectar_uf(nome_zip: str) -> str | None:
    alvo = _sem_acento(nome_zip)
    # Sigla isolada por separador evita casar "PA" dentro de "PARANA".
    for uf in UFS:
        for padrao in (f"_{uf}_", f"_{uf}.", f"-{uf}-", f"-{uf}.", f" {uf} ", f"_{uf}-"):
            if padrao in alvo:
                return uf
    if alvo[:2] in UFS and (len(alvo) == 2 or not alvo[2].isalpha()):
        return alvo[:2]
    compacto = alvo.replace(" ", "").replace("_", "").replace("-", "")
    # Do nome mais longo para o mais curto: "MATO GROSSO DO SUL" antes de "MATO GROSSO".
    for uf, nome in sorted(UF_NAMES.items(), key=lambda kv: -len(kv[1])):
        if _sem_acento(nome).replace(" ", "") in compacto:
            return uf
    return None


def estado_atual() -> dict[str, set[str]]:
    base = RAW_DIR / "car"
    out = {}
    for uf in UFS:
        d = base / uf
        presentes = set()
        if d.exists():
            for sub in d.iterdir():
                if sub.is_dir() and any(sub.rglob("*.shp")) or (
                        sub.is_dir() and any(sub.iterdir())):
                    presentes.add(sub.name)
        out[uf] = presentes
    return out


def imprimir_status():
    est = estado_atual()
    completas = [uf for uf in UFS if all(c in est[uf] for c in CAMADAS_AMBIENTAIS)]
    print(f"[CAR] camada ambiental completa em {len(completas)}/{len(UFS)} UFs: "
          f"{', '.join(completas) or 'nenhuma'}")
    faltam_total = 0
    for uf in UFS:
        faltam = [c for c in CAMADAS_AMBIENTAIS if c not in est[uf]]
        faltam_total += len(faltam)
        if faltam:
            print(f"  {uf}: faltam {len(faltam)} — {', '.join(faltam)}")
    print(f"[CAR] {faltam_total} download(s) restante(s).")


def processar(origem: Path, uf_forcada: str | None, manter: bool):
    zips = sorted(p for p in origem.glob("*.zip") if p.is_file())
    if not zips:
        print(f"Nenhum .zip em {origem}")
        return
    destino_ok = origem / "_organizados"
    extraidos = 0
    for z in zips:
        try:
            with zipfile.ZipFile(z) as zf:
                camada = detectar_camada(zf)
                uf = uf_forcada or detectar_uf(z.name)
                if not camada:
                    print(f"  [?] {z.name}: camada não reconhecida — deixe de lado ou use --uf")
                    continue
                if not uf:
                    print(f"  [?] {z.name}: UF não reconhecida no nome — use --uf")
                    continue
                alvo = RAW_DIR / "car" / uf / camada
                alvo.mkdir(parents=True, exist_ok=True)
                zf.extractall(alvo)
                extraidos += 1
                print(f"  [ok] {z.name} -> data/raw/car/{uf}/{camada}/")
        except zipfile.BadZipFile:
            print(f"  [X] {z.name}: ZIP inválido (download interrompido?)")
            continue
        if not manter:
            destino_ok.mkdir(exist_ok=True)
            shutil.move(str(z), str(destino_ok / z.name))
    print(f"[CAR] {extraidos} arquivo(s) extraído(s).")
    if not manter and extraidos:
        print(f"  Originais movidos para {destino_ok}")
    print()
    imprimir_status()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--origem", type=Path, help="pasta onde os ZIPs foram baixados")
    ap.add_argument("--uf", help="força a UF quando o nome do ZIP não a revela")
    ap.add_argument("--status", action="store_true", help="só mostra o que falta")
    ap.add_argument("--manter", action="store_true", help="não move os ZIPs já extraídos")
    args = ap.parse_args()

    if args.status or not args.origem:
        imprimir_status()
        return
    if args.uf and args.uf.upper() not in UFS:
        raise SystemExit(f"UF inválida: {args.uf}")
    if not args.origem.exists():
        raise SystemExit(f"Pasta não encontrada: {args.origem}")
    processar(args.origem, args.uf.upper() if args.uf else None, args.manter)


if __name__ == "__main__":
    main()
