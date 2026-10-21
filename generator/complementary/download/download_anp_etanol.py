"""
download_anp_etanol.py — baixa o arquivo do Painel Dinâmico de Produtores de Etanol da ANP.

O zip traz a capacidade autorizada de produção de etanol por planta (CNPJ, município,
UF, anidro e hidratado em m³/dia), mês a mês. O process_contas_chave.py usa o último
mês para validar as usinas encontradas na base CNPJ da Receita.

Grava em <brutos>/anp/pb-da-etanol_<AAAA-MM-DD>.zip (data do download), com SHA-256 e
o conteúdo do zip no manifesto data/manifests/raw_anp_etanol.json. Um download novo não
apaga o anterior: o process usa o mais recente.

Uso: python download/download_anp_etanol.py
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import RAW_DIR, sha256_file, today_iso, write_manifest  # noqa: E402

URL = ("https://www.gov.br/anp/pt-br/assuntos/producao-e-fornecimento-de-biocombustiveis/"
       "etanol/arquivos-etanol/pb-da-etanol.zip")
PAGINA = "ANP — Painel Dinâmico de Produtores de Etanol"
DESTINO = RAW_DIR / "anp"


def zip_mais_recente() -> Path | None:
    zs = sorted(DESTINO.glob("pb-da-etanol_*.zip"))
    return zs[-1] if zs else None


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import requests
    try:  # a rede corporativa às vezes troca o certificado; o truststore usa o do Windows
        import truststore
        truststore.inject_into_ssl()
    except ImportError:
        pass
    DESTINO.mkdir(parents=True, exist_ok=True)
    alvo = DESTINO / f"pb-da-etanol_{today_iso()}.zip"
    tmp = alvo.with_suffix(".part")
    with requests.get(URL, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(tmp, "wb") as fh:
            for bloco in r.iter_content(1 << 20):
                fh.write(bloco)
    with zipfile.ZipFile(tmp) as z:          # zip ruim falha aqui, antes de substituir
        conteudo = z.namelist()
    tmp.replace(alvo)
    sha = sha256_file(alvo)
    write_manifest("raw_anp_etanol", source=f"{PAGINA} ({URL})", reference_date=None,
                   source_files=[str(alvo)], row_count=len(conteudo),
                   extra={"url": URL, "arquivo": alvo.name, "sha256": sha, "conteudo_zip": conteudo,
                          "bytes": alvo.stat().st_size})
    print(f"  {alvo.name}: {alvo.stat().st_size / 1e6:.2f} MB · sha256 {sha[:16]}… · {conteudo}")


if __name__ == "__main__":
    main()
