# contas.py
# Contas dos clientes da loja: cadastro, login (CPF + senha) e "Minha conta"
# com os dados do cliente e o historico de pedidos.
# Projeto: Quilombo Doces

from flask import (Blueprint, request, render_template, redirect, url_for,
                   session, flash)
from werkzeug.security import generate_password_hash, check_password_hash

from cadastro_sqlite import conectar_banco

# "Blueprint" = um pedaco do site separado do app.py; e ligado la com
# app.register_blueprint(contas). Nos templates: url_for('contas.entrar') etc.
contas = Blueprint("contas", __name__)


# --------------------------------------------------------------- AJUDANTES

def so_numeros(texto):
    """Tira pontos, tracos, espacos e parenteses: "396.560.598-40" -> "39656059840"."""
    return "".join(c for c in texto if c.isdigit())


def validar_cpf(cpf):
    """Confere os 2 digitos verificadores do CPF (aceita com ou sem pontos)."""
    n = so_numeros(cpf)
    if len(n) != 11 or n == n[0] * 11:      # 111.111.111-11 etc. nao valem
        return False
    for i in (9, 10):                       # posicao do 1o e do 2o digito
        soma = sum(int(n[j]) * (i + 1 - j) for j in range(i))
        if soma * 10 % 11 % 10 != int(n[i]):
            return False
    return True


@contas.app_template_filter("cpf")
def formatar_cpf(cpf):
    """Mostra "39656059840" como "396.560.598-40" (nos templates: {{ x|cpf }})."""
    n = so_numeros(cpf or "")
    if len(n) != 11:
        return cpf or ""
    return f"{n[:3]}.{n[3:6]}.{n[6:9]}-{n[9:]}"


def endereco_completo(cliente):
    """Junta os campos do endereco numa linha so (vai junto com o pedido)."""
    rua = cliente["endereco"]
    if cliente["numero"]:
        rua += f", {cliente['numero']}"
    if cliente["complemento"]:
        rua += f", {cliente['complemento']}"
    return f"{rua} - {cliente['bairro']}, {cliente['cidade']} - CEP {cliente['cep']}"

def cliente_atual():
    """Cliente logado (linha da tabela clientes) ou None se ninguem entrou."""
    id_cliente = session.get("cliente_id")
    if not id_cliente:
        return None

    conn = conectar_banco()
    cliente = conn.execute('SELECT * FROM clientes WHERE id = ?',
                           (id_cliente,)).fetchone()
    conn.close()

    if cliente is None:                     # conta apagada: sai da sessao
        session.pop("cliente_id", None)
    return cliente


def destino_seguro(proximo):
    """Para onde voltar depois do login (so enderecos do proprio site)."""
    if proximo and proximo.startswith("/") and not proximo.startswith("//"):
        return proximo
    return url_for("contas.minha_conta")


def ler_cadastro():
    """Le os campos do formulario de cadastro e devolve um dicionario limpo."""
    campos = ("nome", "cpf", "telefone", "endereco", "numero", "complemento",
              "bairro", "cidade", "cep")
    return {c: request.form.get(c, "").strip() for c in campos}


def validar_cadastro(dados, conn, id_atual=None, senha_obrigatoria=True):
    """Devolve {campo: mensagem}; vazio = tudo certo."""
    erros = {}

    if len(dados["nome"]) < 2:
        erros["nome"] = "Informe seu nome completo."

    if not validar_cpf(dados["cpf"]):
        erros["cpf"] = "CPF invalido. Confira os numeros."
    else:
        existente = conn.execute(
            'SELECT id FROM clientes WHERE cpf = ? AND id <> ?',
            (so_numeros(dados["cpf"]), id_atual or 0)).fetchone()
        if existente:
            erros["cpf"] = "Ja existe uma conta com esse CPF. Tente entrar."

    if len(so_numeros(dados["telefone"])) < 10:
        erros["telefone"] = "Informe o WhatsApp com DDD (ex.: 11 99999-9999)."
    if len(dados["endereco"]) < 3:
        erros["endereco"] = "Informe a rua."
    if not dados["numero"]:
        erros["numero"] = "Informe o numero (ou S/N se nao tiver)."
    if len(dados["bairro"]) < 2:
        erros["bairro"] = "Informe o bairro."
    if len(dados["cidade"]) < 2:
        erros["cidade"] = "Informe a cidade."
    if len(so_numeros(dados["cep"])) != 8:
        erros["cep"] = "O CEP tem 8 numeros (ex.: 01234-567)."

    senha = request.form.get("senha", "")
    if senha_obrigatoria or senha:
        if len(senha) < 6:
            erros["senha"] = "A senha precisa ter pelo menos 6 caracteres."
        elif senha != request.form.get("confirmar", ""):
            erros["senha"] = "As duas senhas nao sao iguais."

    return erros


# --------------------------------------------------------------- PAGINAS

@contas.route("/conta")
def minha_conta():
    """Aba "Minha conta": login (se ninguem entrou) ou dados + historico."""
    cliente = cliente_atual()
    if cliente is None:
        return render_template("conta_entrar.html", proximo="", erro="")

    conn = conectar_banco()
    pedidos = conn.execute(
        'SELECT * FROM pedidos WHERE cliente_id = ? ORDER BY id DESC',
        (cliente["id"],)).fetchall()
    conn.close()

    return render_template("conta.html", cliente=cliente, pedidos=pedidos)


@contas.route("/conta/entrar", methods=["GET", "POST"])
def entrar():
    """Login com CPF + senha. "proximo" = pagina para voltar depois."""
    proximo = request.values.get("proximo", "")

    if request.method == "GET":
        if cliente_atual():                 # ja entrou: vai direto
            return redirect(destino_seguro(proximo))
        return render_template("conta_entrar.html", proximo=proximo, erro="")

    conn = conectar_banco()
    cliente = conn.execute('SELECT * FROM clientes WHERE cpf = ?',
                           (so_numeros(request.form.get("cpf", "")),)).fetchone()
    conn.close()

    if cliente is None or not check_password_hash(cliente["senha_hash"],
                                                  request.form.get("senha", "")):
        return render_template("conta_entrar.html", proximo=proximo,
                               cpf=request.form.get("cpf", ""),
                               erro="CPF ou senha incorretos."), 400

    session["cliente_id"] = cliente["id"]
    flash(f"Olá, {cliente['nome'].split()[0]}! Você entrou na sua conta.")
    return redirect(destino_seguro(proximo))


@contas.route("/conta/cadastro", methods=["GET", "POST"])
def cadastro():
    """Criar conta. Depois de cadastrar, ja entra e volta para "proximo"."""
    proximo = request.values.get("proximo", "")

    if request.method == "GET":
        return render_template("conta_cadastro.html", titulo="Criar conta",
                               dados={}, erros={}, proximo=proximo, editando=False)

    dados = ler_cadastro()
    conn = conectar_banco()
    erros = validar_cadastro(dados, conn)

    if erros:
        conn.close()
        return render_template("conta_cadastro.html", titulo="Criar conta",
                               dados=dados, erros=erros, proximo=proximo,
                               editando=False), 400

    cursor = conn.execute(

        'INSERT INTO clientes (nome, cpf, telefone, endereco, numero, complemento, '
        'bairro, cidade, cep, senha_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (dados["nome"], so_numeros(dados["cpf"]), dados["telefone"],
         dados["endereco"], dados["numero"], dados["complemento"], dados["bairro"],
         dados["cidade"], dados["cep"],
         generate_password_hash(request.form["senha"])))
    conn.commit()
    conn.close()

    session["cliente_id"] = cursor.lastrowid
    flash("Conta criada com sucesso!")
    return redirect(destino_seguro(proximo))


@contas.route("/conta/editar", methods=["GET", "POST"])
def editar():
    """Alterar os dados do cadastro (a senha so muda se preencher)."""
    cliente = cliente_atual()
    if cliente is None:
        return redirect(url_for("contas.entrar", proximo=url_for("contas.editar")))

    proximo = request.values.get("proximo", "")

    if request.method == "GET":
        return render_template("conta_cadastro.html", titulo="Meus dados",
                               dados=dict(cliente), erros={}, proximo=proximo,
                               editando=True)

    dados = ler_cadastro()
    conn = conectar_banco()
    erros = validar_cadastro(dados, conn, id_atual=cliente["id"],
                             senha_obrigatoria=False)

    if erros:
        conn.close()
        return render_template("conta_cadastro.html", titulo="Meus dados",
                               dados=dados, erros=erros, proximo=proximo,
                               editando=True), 400

    conn.execute(
        'UPDATE clientes SET nome = ?, cpf = ?, telefone = ?, endereco = ?, '
        'numero = ?, complemento = ?, bairro = ?, cidade = ?, cep = ? WHERE id = ?',
        (dados["nome"], so_numeros(dados["cpf"]), dados["telefone"],
         dados["endereco"], dados["numero"], dados["complemento"], dados["bairro"],
         dados["cidade"], dados["cep"], cliente["id"]))
    if request.form.get("senha"):
        conn.execute('UPDATE clientes SET senha_hash = ? WHERE id = ?',
                     (generate_password_hash(request.form["senha"]), cliente["id"]))
    conn.commit()
    conn.close()

    flash("Dados atualizados!")
    return redirect(destino_seguro(proximo))


@contas.route("/conta/sair", methods=["POST"])
def sair():
    session.pop("cliente_id", None)
    flash("Você saiu da sua conta.")
    return redirect(url_for("loja"))