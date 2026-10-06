# validacoes.py
# Modulo de validacoes — reutilizado em todas as versoes do sistema
# Projeto: Quilombo Doces

import math


def validar_nome(nome):
    """Valida se o nome do doce tem pelo menos 2 caracteres."""
    return len(nome.strip()) >= 2


def validar_preco(preco_str):
    """Valida se o preco e um numero maior que zero (aceita 18.5 ou 18,50)."""
    try:
        preco = float(preco_str.replace(",", "."))
        return math.isfinite(preco) and preco > 0
    except ValueError:
        return False


def doce_ja_existe(nome, lista_doces):
    """Verifica se o doce ja esta cadastrado na lista."""
    for doce in lista_doces:
        if doce["nome"].lower() == nome.lower():
            return True
    return False


# Este bloco SO roda quando executamos: python validacoes.py
# Quando o arquivo e importado por outro modulo, ele nao roda.
if __name__ == "__main__":
    print("Testes rapidos de validacoes.py")
    print(validar_nome("Brigadeiro"))             # True
    print(validar_nome("a"))                      # False
    print(validar_preco("18,50"))                 # True
    print(validar_preco("abc"))                   # False
    print(validar_preco("-3"))                    # False
    print(doce_ja_existe("cocada", [{"nome": "Cocada"}]))   # True
