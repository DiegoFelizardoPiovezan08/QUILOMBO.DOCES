# cadastro_sqlite.py
# Sistema de cadastro de doces com persistencia em SQLite — CRUD completo
# Projeto: Quilombo Doces

import sqlite3
import os

#valida se valor é um preço validp
def validar_preco(texto):
    """Retorna True se o texto for um preco valido (numero maior que zero)."""
    try:
        return float(texto.replace(",", ".")) > 0
    except ValueError:
        return False

#cria a tabela e faz o usuario inserir o id, nome e preço
def conectar_banco():
    """Conecta ao banco SQLite e cria a tabela se nao existir."""
    os.makedirs('dados', exist_ok=True)
    conn = sqlite3.connect('dados/cadastro.db')
    conn.row_factory = sqlite3.Row      # permite acessar as colunas pelo nome

    conn.execute('''
        CREATE TABLE IF NOT EXISTS doces (
            id     INTEGER PRIMARY KEY AUTOINCREMENT,
            nome   TEXT    NOT NULL,
            preco  REAL    NOT NULL
        )
    ''')

    conn.execute('''
            CREATE TABLE IF NOT EXISTS eventos (
                id     INTEGER PRIMARY KEY AUTOINCREMENT,
                nome   TEXT    NOT NULL,
                descricao TEXT 
            )
        ''')
    conn.commit()
    return conn


def mostrar_menu():
    """Exibe o menu principal do sistema SQLite."""
    print("\n" + "=" * 50)
    print("  SISTEMA DE CADASTRO DE DOCES")
    print("=" * 50)
    print("1. Cadastrar doce")
    print("2. Listar doces")
    print("3. Buscar doce")
    print("4. Editar doce")
    print("5. Excluir doce")
    print("6. Sair")
    print("=" * 50)


def pausar():
    """Pausa a execucao aguardando ENTER."""
    input("\nPressione ENTER para continuar...")

#procura se o id existe a partir da ordem de cadastro
def escolher_id(conn, acao):
    """Mostra os registros e devolve o id escolhido (ou None se cancelar)."""
    registros = conn.execute(
        'SELECT id, nome, preco FROM doces ORDER BY id').fetchall()

    #se não existir nenhum registro
    if len(registros) == 0:
        print("\nNenhum doce cadastrado.")
        return None

    #procurar doce pelo nome
    print(f"\nEscolha qual doce deseja {acao}:")
    print("-" * 50)
    for reg in registros:
        print(f"  {reg['id']} — {reg['nome']} (R$ {reg['preco']:.2f})")
    print("-" * 50)

    #se o id nao existir fica invalido ou cancela a operação
    escolha = input("\nDigite o ID (ou ENTER para cancelar): ").strip()
    if escolha == "":
        print("Operacao cancelada.")
        return None
    if not escolha.isdigit():
        print("ID invalido!")
        return None

    id_escolhido = int(escolha)
    existe = conn.execute('SELECT id FROM doces WHERE id = ?',
                          (id_escolhido,)).fetchone()
    if existe is None:
        print(f"Nao existe registro com ID {id_escolhido}!")
        return None

    return id_escolhido


def cadastrar_doce():
    """Cadastra um novo doce no banco SQLite com validacoes. (Create)"""
    print("\n" + "-" * 40)
    print("  CADASTRO DE NOVO DOCE ")
    print("-" * 40)

    conn = conectar_banco()

    #verifica se o doce segue as especificações de tamanho ou se ja esta cadastrado
    while True:
        nome = input("Nome do doce: ").strip()
        if len(nome) < 2:
            print("Erro: Nome deve ter pelo menos 2 caracteres!")
            continue
        existente = conn.execute(
            'SELECT id FROM doces WHERE LOWER(nome) = ?',
            (nome.lower(),)
        ).fetchone()
        if existente:
            print("Erro: Este doce ja esta cadastrado!")
            continue
        break

    #permite que o preço seja escrita forma que o usuário quiser e que seja > 0
    while True:
        preco_str = input("Preco (exemplo: 18,50): ").strip()
        if validar_preco(preco_str):
            preco = round(float(preco_str.replace(",", ".")), 2)
            break
        print("Erro: Preco deve ser um numero maior que zero!")

    #cadastra o doce e verifica os erros
    try:
        conn.execute(
            'INSERT INTO doces (nome, preco) VALUES (?, ?)',
            (nome.title(), preco)
        )
        conn.commit()
        print(f"\n'{nome.title()}' cadastrado com sucesso no banco!")
    except sqlite3.Error as e:
        print(f"\nErro ao cadastrar no banco: {e}")
    finally:
        conn.close()

    pausar()


def listar_doces():
    """Lista todos os doces do banco SQLite. (Read)"""
    conn = conectar_banco()

    registros = conn.execute('SELECT * FROM doces ORDER BY nome').fetchall()

    #verifica se exsite algum doce registro
    if len(registros) == 0:
        print("\nNenhum doce cadastrado ainda.")
        conn.close()
        pausar()
        return
    
    #lista os doces na tabela
    print("\n" + "-" * 60)
    print(f"  LISTA DE DOCES CADASTRADOS ({len(registros)} registros)")
    print("-" * 60)

    for reg in registros:
        # Com row_factory, acessamos as colunas pelo nome
        print(f"\n  ID: {reg['id']} | Doce: {reg['nome']}")
        print(f"  Preco: R$ {reg['preco']:.2f}")
        print("-" * 40)

        conn.close()
        pausar()


def buscar_doce():
    """Busca doces no banco por nome ou por preco maximo. (Read)"""
    conn = conectar_banco()

    #verifica se possui algum doce no registro
    total = conn.execute('SELECT COUNT(*) FROM doces').fetchone()[0]
    if total == 0:
        print("\nNenhum doce cadastrado para buscar.")
        conn.close()
        pausar()
        return

    #procura os doces pelo nome e/ou preço
    print("\n" + "-" * 40)
    print("  BUSCAR DOCE")
    print("-" * 40)
    print("1. Buscar por nome")
    print("2. Buscar por preco")

    #verifica se é uma opção válida
    while True:
        opcao = input("\nEscolha (1-2): ").strip()
        if opcao in ['1', '2']:
            break
        print("Opcao invalida! Escolha 1 ou 2.")

    #se digitar 1 --> procura pelo nome
    if opcao == '1':
        termo = input("Digite o nome para buscar: ").strip().lower()
        encontrados = conn.execute(
            'SELECT * FROM doces WHERE LOWER(nome) LIKE ? ORDER BY nome',
            (f'%{termo}%',)
        ).fetchall()
    #se digitar 2 --> procura pelo preço, verifica se é < 0
    else:
        while True:
            termo = input("Digite o preco: ").strip()
            if validar_preco(termo):
                break
            print("Erro: Preco deve ser um numero maior que zero!")
        encontrados = conn.execute(
            'SELECT * FROM doces WHERE preco = ? ORDER BY preco',
            (float(termo.replace(",", ".")),)
        ).fetchall()

    #caso não exista doces
    if len(encontrados) == 0:
        print(f"\nNenhum doce encontrado com '{termo}'")
    else:
        print(f"\n{len(encontrados)} doce(s) encontrado(s):")
        print("-" * 50)
        for reg in encontrados:
            print(f"  ID: {reg['id']} | {reg['nome']} — R$ {reg['preco']:.2f}")
            print("-" * 30)

    conn.close()
    pausar()


def editar_doce():
    """Altera os dados de um doce ja cadastrado. (Update)"""
    conn = conectar_banco()

    id_escolhido = escolher_id(conn, "editar")
    if id_escolhido is None:
        conn.close()
        pausar()
        return

    doce = conn.execute('SELECT * FROM doces WHERE id = ?',
                        (id_escolhido,)).fetchone()

    #edita os valores dos produtos
    print("\n" + "-" * 40)
    print(f"  EDITANDO: {doce['nome']}")
    print("-" * 40)
    print("Deixe em branco para manter o valor atual.\n")

    while True:
        #faz com que o novo nome se torne o oficial
        novo_nome = input(f"Nome [{doce['nome']}]: ").strip()
        if novo_nome == "":
            novo_nome = doce['nome']
            break
        #avalia se tem mais de 2 caracteres
        if len(novo_nome) < 2:
            print("Erro: Nome deve ter pelo menos 2 caracteres!")
            continue
        # O proprio registro nao conta como duplicata
        existente = conn.execute(
            'SELECT id FROM doces WHERE LOWER(nome) = ? AND id <> ?',
            (novo_nome.lower(), id_escolhido)
        ).fetchone()
        #se ja existir o mesmo doce da erro
        if existente:
            print("Erro: Ja existe outro doce com esse nome!")
            continue
        novo_nome = novo_nome.title()
        break

    while True:
        #o novo preço se torna o oficial
        novo_preco = input(f"Preco [{doce['preco']:.2f}]: ").strip()
        if novo_preco == "":
            novo_preco = doce['preco']
            break
        #valida o preço
        if validar_preco(novo_preco):
            novo_preco = round(float(novo_preco.replace(",", ".")), 2)
            break
        print("Erro: Preco deve ser um numero maior que zero!")

    try:
        conn.execute(
            'UPDATE doces SET nome = ?, preco = ? WHERE id = ?',
            (novo_nome, novo_preco, id_escolhido)
        )
        conn.commit()
        #mostra se deu certo ao atualizar o nome
        print(f"\nDados de '{novo_nome}' atualizados com sucesso!")
    except sqlite3.Error as e:
        print(f"\nErro ao atualizar no banco: {e}")
    finally:
        conn.close()

    pausar()


def excluir_doce():
    """Remove um doce do banco, com confirmacao. (Delete)"""
    conn = conectar_banco()

    id_escolhido = escolher_id(conn, "excluir")
    if id_escolhido is None:
        conn.close()
        pausar()
        return

    doce = conn.execute('SELECT * FROM doces WHERE id = ?',
                        (id_escolhido,)).fetchone()

    #exclui algum registro
    print("\n" + "-" * 40)
    print("  ATENCAO — voce vai EXCLUIR o registro:")
    print("-" * 40)
    print(f"  ID: {doce['id']} | {doce['nome']}")
    print(f"  Preco: R$ {doce['preco']:.2f}")
    print("-" * 40)
    print("Esta acao NAO pode ser desfeita.")

    #para nao ocorrer erros ele garante que a pessoa realmente quer excluir
    confirmacao = input("\nConfirma a exclusao? (s/N): ").strip().lower()

    if confirmacao != "s":
        print("\nOperacao cancelada. Nada foi excluido.")
    else:
        conn.execute('DELETE FROM doces WHERE id = ?', (id_escolhido,))
        conn.commit()
        print(f"\nRegistro de '{doce['nome']}' excluido.")

    conn.close()
    pausar()