# geolocalizacao.py
# Descobre onde fica um CEP (latitude e longitude) e calcula a distancia
# ate a loja, para cobrar o frete pela tabela de km.
# Usa servicos gratis, sem cadastro e sem chave:
#   1. AwesomeAPI de CEP  (ja devolve a localizacao do CEP)
#   2. se nao achar: ViaCEP (endereco do CEP) + OpenStreetMap/Nominatim
#      (localizacao do endereco)
# Cada CEP encontrado fica guardado no banco: na proxima vez nao precisa
# perguntar de novo para a internet.
# Projeto: Quilombo Doces

import json
import math
from urllib.parse import quote
from urllib.request import Request, urlopen

# a distancia e calculada em linha reta; pelas ruas o caminho e mais longo.
# Em cidade grande, somar uns 30% chega perto da distancia de carro.
FATOR_RUAS = 1.3

# identificacao do site nos pedidos (o OpenStreetMap exige uma)
NAVEGADOR = "QuilomboDoces/1.0 (loja de doces artesanais)"


def so_digitos(texto):
    return "".join(c for c in (texto or "") if c.isdigit())


def baixar_json(url):
    """Abre o endereco e devolve o JSON da resposta (ou None se der erro)."""
    try:
        pedido = Request(url, headers={"User-Agent": NAVEGADOR})
        with urlopen(pedido, timeout=8) as resposta:
            return json.loads(resposta.read().decode("utf-8"))
    except Exception as erro:            # sem internet, servico fora do ar etc.
        print(f"[geolocalizacao] {url}: {erro}")
        return None


def buscar_na_internet(cep):
    """(latitude, longitude) do CEP, perguntando aos servicos gratis."""
    # 1) AwesomeAPI: o CEP ja vem com lat/lng
    dados = baixar_json(f"https://cep.awesomeapi.com.br/json/{cep}")
    if dados and dados.get("lat") and dados.get("lng"):
        return float(dados["lat"]), float(dados["lng"])

    # 2) ViaCEP da a rua/cidade; o Nominatim acha a localizacao do endereco
    endereco = baixar_json(f"https://viacep.com.br/ws/{cep}/json/")
    if not endereco or endereco.get("erro"):
        return None
    partes = [endereco.get("logradouro"), endereco.get("bairro"),
              endereco.get("localidade"), endereco.get("uf"), "Brasil"]
    busca = ", ".join(p for p in partes if p)
    achados = baixar_json("https://nominatim.openstreetmap.org/search?format=json"
                          f"&limit=1&countrycodes=br&q={quote(busca)}")
    if achados:
        return float(achados[0]["lat"]), float(achados[0]["lon"])
    return None


def coordenadas_do_cep(conn, cep):
    """(latitude, longitude) do CEP, ou None se nao achar.
    Procura primeiro no banco (cache) e so depois na internet."""
    cep = so_digitos(cep)
    if len(cep) != 8:
        return None

    salvo = conn.execute('SELECT lat, lon FROM cep_coordenadas WHERE cep = ?',
                         (cep,)).fetchone()
    if salvo:
        return salvo["lat"], salvo["lon"]

    achado = buscar_na_internet(cep)
    if achado:
        conn.execute('INSERT OR REPLACE INTO cep_coordenadas (cep, lat, lon) '
                     'VALUES (?, ?, ?)', (cep, achado[0], achado[1]))
        conn.commit()
    return achado


def distancia_km(origem, destino):
    """Distancia aproximada de carro, em km, entre dois pontos (lat, lon):
    linha reta (formula de Haversine) + 30% pelas ruas."""
    lat1, lon1 = map(math.radians, origem)
    lat2, lon2 = map(math.radians, destino)
    a = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    linha_reta = 2 * 6371 * math.asin(math.sqrt(a))     # 6371 km = raio da Terra
    return round(linha_reta * FATOR_RUAS, 1)
