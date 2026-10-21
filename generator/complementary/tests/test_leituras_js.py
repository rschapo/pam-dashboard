"""As regras de cálculo e de classe do mapa ficam em public/js/leituras.js, funções puras
que o navegador usa. Aqui elas rodam em node, com valores conferidos à mão."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

LEITURAS = Path(__file__).resolve().parents[3] / "public" / "js" / "leituras.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node ausente: as regras do front não rodam aqui")


def _js(expr: str):
    """Avalia uma expressão com LEITURAS carregado e devolve o resultado em JSON."""
    prog = f"const L = require({json.dumps(str(LEITURAS))}); process.stdout.write(JSON.stringify({expr}));"
    r = subprocess.run([NODE, "-e", prog], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_densidade_de_estado_e_soma_sobre_soma_e_nao_media_de_densidades():
    # Dois municípios: 1.000 ha em 10 km² (100 ha/km²) e 1.000 ha em 1.000 km² (1 ha/km²).
    # A média das densidades daria 50,5; o recorte tem 2.000 ha em 1.010 km².
    assert _js("L.densidade([1000, 1000], [1000, 100000])") == pytest.approx(2000 / 1010)
    assert _js("L.densidade([null, null], [1000])") is None          # sem área publicada: sem medida
    assert _js("L.densidade([0], [1000])") == 0                      # com PAM e sem a cultura: zero
    assert _js("L.densidade([5], [0])") is None                      # sem território


def test_vocacao_e_a_parte_da_area_colhida_do_proprio_territorio():
    assert _js("L.vocacao(250, 1000)") == 25
    assert _js("L.vocacao(0, 1000)") == 0
    assert _js("L.vocacao(10, 0)") is None


def test_quantis_so_com_positivos_nao_colapsam_com_muitos_zeros():
    # 90 zeros e 10 valores: quantis sobre todos dariam cortes 0; só com positivos não.
    vals = "Array(90).fill(0).concat([1,2,3,4,5,6,7,8,9,10]).concat([null, null])"
    cortes = _js(f"L.classesQuantis({vals}, 5)")
    assert cortes == [3, 5, 7, 9]
    assert all(c > 0 for c in cortes)
    assert _js(f"L.classe(0, {cortes})") == 0                        # zero na primeira classe
    assert _js(f"L.classe(null, {cortes})") == -1                    # ausente fora das classes (cinza)
    assert _js(f"L.classe(10, {cortes})") == 4
    assert _js("L.classesQuantis([0, 0, null], 5)") == []            # nada positivo: sem classes
    assert _js("L.classesQuantis([2, 2, 2, 2, 2, 2], 5)") == [2]     # cortes repetidos viram um


def test_rotulos_e_casas_decimais_pela_ordem_de_grandeza():
    assert _js("L.casas([0.03, 0.2, 1.5])") == 3                     # 0,03 não vira "0,0"
    assert _js("L.casas([12, 40, 300])") == 0
    assert _js("L.casas([1.21, 1.24])") == 2                         # vizinhos iguais com 1 casa ganham outra
    fmt = "x => x.toLocaleString('pt-BR', { maximumFractionDigits: L.casas([0.03, 0.2]) })"
    assert _js(f"L.rotulosClasses([0.03, 0.2], {fmt})") == ["0 a < 0,03", "0,03 a < 0,2", "≥ 0,2"]
    # cada corte na própria ordem de grandeza, com dois algarismos significativos
    cortes = "[0.0024, 0.0379, 0.135, 1.1554, 2.005, 2.5364, 1250.4]"
    assert _js(f"[...L.textosCortes({cortes}).values()]") == ["0,0024", "0,038", "0,14", "1,2", "2", "2,5", "1.250"]
    assert _js("[...L.textosCortes([1.21, 1.24]).values()]") == ["1,21", "1,24"]   # vizinhos distintos


def test_cor_da_classe_espalha_a_rampa():
    pal = "['a','b','c','d','e','f','g']"
    assert _js(f"[0,1,2].map(i => L.corDaClasse(i, 3, {pal}))") == ["a", "d", "g"]
    assert _js(f"L.corDaClasse(-1, 3, {pal})") is None


def test_dominante_e_soma_de_categorias():
    ordem = "['Cana','Grãos e oleaginosas','Floresta plantada']"
    assert _js(f"L.dominante({{'Cana': 5, 'Floresta plantada': 9}}, {ordem})") == "Floresta plantada"
    assert _js(f"L.dominante({{'Cana': 5, 'Grãos e oleaginosas': 5}}, {ordem})") == "Cana"   # empate: ordem
    assert _js(f"L.dominante({{}}, {ordem})") is None
    assert _js("L.somaCategorias([{c: {Cana: 1}}, {c: {Cana: 2, Café: 1}}, null])") == {"Cana": 3, "Café": 1}
