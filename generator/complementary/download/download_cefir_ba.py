"""
download_cefir_ba.py — camadas do CEFIR (cadastro ambiental da Bahia) pelo WFS do Inema.

O SICAR da Bahia é o próprio CEFIR, mas o CEFIR registra o imóvel de outro jeito:
não tem camada de área consolidada para imóvel privado — tem "atividades
desenvolvidas" — e guarda as áreas degradadas de reserva legal e APP em camadas
próprias, que o SICAR não repassa. Ver docs/CAR_LIMITATIONS.md.

WFS público, sem CAPTCHA. A paginação é por faixa de gid e não por startIndex: a
base é atualizada todo dia, e um registro removido no meio do download deslocaria
todas as páginas seguintes. Cada faixa é validada pela contagem do próprio
servidor antes de ser aceita, e o download retoma de onde parou.

A camada de limites traz nome do imóvel e do proprietário. Dela só se pedem
ide_imovel, numero_car (com o código IBGE do município embutido) e status.

Uso:
  python download_cefir_ba.py
  python download_cefir_ba.py --camadas atividade_desenvolvida
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import RAW_DIR, today_iso, write_manifest  # noqa: E402

WFS = "http://geoserver.inema.ba.gov.br/geoserver/wfs"  # HTTPS não responde
ESPACO = "Vetor_Recortes_Tematicos"
DESTINO = RAW_DIR / "cefir" / "BA"
FAIXA = 20_000
PAUSA = 1.0

CAMADAS = {
    "atividade_desenvolvida": "cefir_imovel_rural_atividade_desenvolvida_inema",
    "area_degradada_reserva_legal": "cefir_imovel_rural_area_degradada_reserva_legal_inema",
    "area_degradada_app": "cefir_imovel_rural_area_degradada_app_inema",
}
LIMITE = "cefir_imovel_rural_limite_inema"
CAMPOS_LIMITE = ["gid", "ide_imovel", "numero_car", "status"]


def _pedir(camada: str, tentativas: int = 4, **params) -> bytes:
    base = {"service": "WFS", "version": "2.0.0", "request": "GetFeature",
            "typeNames": f"{ESPACO}:{camada}"}
    url = f"{WFS}?{urllib.parse.urlencode({**base, **params})}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (pam-dashboard)"})
    for t in range(1, tentativas + 1):
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                return r.read()
        except Exception as e:
            if t == tentativas:
                raise
            print(f"      tentativa {t} falhou ({type(e).__name__}); nova em {15 * t}s", flush=True)
            time.sleep(15 * t)
    raise RuntimeError("inalcançável")


def _contar(camada: str, filtro: str | None = None) -> int:
    extra = {"CQL_FILTER": filtro} if filtro else {}
    txt = _pedir(camada, resultType="hits", **extra).decode("utf-8", "replace")
    return int(txt.split('numberMatched="')[1].split('"')[0])


def _gid_max(camada: str) -> int:
    d = json.loads(_pedir(camada, outputFormat="application/json",
                          propertyName="gid", sortBy="gid D", count=1))
    return int(d["features"][0]["properties"]["gid"])


def baixar_camada(nome: str, camada: str) -> dict:
    import pyogrio
    pasta = DESTINO / nome
    pasta.mkdir(parents=True, exist_ok=True)
    total = _contar(camada)
    topo = _gid_max(camada)
    faixas = [(a, min(a + FAIXA, topo + 1)) for a in range(1, topo + 1, FAIXA)]
    print(f"[CEFIR] {nome}: {total:,} feições, gid até {topo:,}, {len(faixas)} faixa(s)", flush=True)

    recebidas, t0 = 0, time.time()
    for i, (a, b) in enumerate(faixas, 1):
        alvo = pasta / f"gid_{a:07d}_{b - 1:07d}"
        pronto = alvo / ".ok"
        if pronto.exists():
            recebidas += int(pronto.read_text())
            continue
        filtro = f"gid >= {a} AND gid < {b}"
        esperado = _contar(camada, filtro)
        if esperado == 0:
            alvo.mkdir(exist_ok=True)
            pronto.write_text("0")
            continue
        for tentativa in range(3):
            conteudo = _pedir(camada, outputFormat="SHAPE-ZIP", CQL_FILTER=filtro)
            if alvo.exists():
                shutil.rmtree(alvo)
            alvo.mkdir(parents=True)
            with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
                zf.extractall(alvo)
            shp = next(alvo.glob("*.shp"), None)
            obtido = pyogrio.read_info(shp)["features"] if shp else 0
            if obtido == esperado:
                break
            print(f"      faixa {a}-{b - 1}: {obtido} de {esperado}; repetindo", flush=True)
            time.sleep(10)
        else:
            raise RuntimeError(f"{nome} faixa {a}-{b - 1}: contagem não fecha após 3 tentativas")
        pronto.write_text(str(obtido))
        recebidas += obtido
        decorrido = time.time() - t0
        print(f"   [{i}/{len(faixas)}] gid {a:,}-{b - 1:,}: {obtido:,} feições "
              f"({len(conteudo) / 1e6:.0f} MB, {decorrido / 60:.0f} min)", flush=True)
        time.sleep(PAUSA)

    ok = recebidas == total
    print(f"[CEFIR] {nome}: {recebidas:,} de {total:,} feições "
          f"{'— completo' if ok else '— DIVERGE (a base mudou durante o download?)'}", flush=True)
    return {"camada": nome, "feicoes": recebidas, "esperado": total, "completo": ok}


def baixar_limite() -> dict:
    """Só identificador, número do CAR e status — sem nome de imóvel nem de pessoa."""
    DESTINO.mkdir(parents=True, exist_ok=True)
    alvo = DESTINO / "limite_atributos.csv"
    if alvo.exists() and (DESTINO / "limite_atributos.ok").exists():
        n = sum(1 for _ in open(alvo, encoding="utf-8")) - 1
        print(f"[CEFIR] limite: já baixado ({n:,} linhas)", flush=True)
        return {"camada": "limite_atributos", "feicoes": n, "completo": True}
    total = _contar(LIMITE)
    topo = _gid_max(LIMITE)
    passo = 200_000
    linhas = 0
    with open(alvo, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(CAMPOS_LIMITE)
        for a in range(1, topo + 1, passo):
            b = min(a + passo, topo + 1)
            txt = _pedir(LIMITE, outputFormat="csv", propertyName=",".join(CAMPOS_LIMITE[1:]),
                         CQL_FILTER=f"gid >= {a} AND gid < {b}").decode("utf-8", "replace")
            for r in csv.DictReader(io.StringIO(txt)):
                # O CSV do GeoServer traz FID na frente e o gid dentro dele.
                gid = r.get("gid") or str(r.get("FID", "")).rsplit(".", 1)[-1]
                w.writerow([gid, r.get("ide_imovel"), r.get("numero_car"), r.get("status")])
                linhas += 1
            print(f"   limite gid {a:,}-{b - 1:,}: {linhas:,} linhas acumuladas", flush=True)
            time.sleep(PAUSA)
    ok = linhas == total
    if ok:
        (DESTINO / "limite_atributos.ok").write_text(str(linhas))
    print(f"[CEFIR] limite: {linhas:,} de {total:,} {'— completo' if ok else '— DIVERGE'}", flush=True)
    return {"camada": "limite_atributos", "feicoes": linhas, "esperado": total, "completo": ok}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--camadas", nargs="*", default=list(CAMADAS) + ["limite"])
    args = ap.parse_args()

    resultados = []
    for nome in args.camadas:
        if nome == "limite":
            resultados.append(baixar_limite())
        elif nome in CAMADAS:
            resultados.append(baixar_camada(nome, CAMADAS[nome]))
        else:
            raise SystemExit(f"camada desconhecida: {nome}")

    arquivos = [str(p) for p in DESTINO.rglob("*") if p.is_file() and p.suffix in (".shp", ".csv")]
    write_manifest("raw_cefir_ba", source=f"Inema/CEFIR — WFS {WFS}", reference_date=today_iso(),
                   source_files=arquivos,
                   warnings=[f"{r['camada']}: {r['feicoes']} de {r.get('esperado')}"
                             for r in resultados if not r["completo"]])
    print("[CEFIR] concluído:", ", ".join(f"{r['camada']} {'ok' if r['completo'] else 'DIVERGE'}"
                                          for r in resultados), flush=True)


if __name__ == "__main__":
    main()
