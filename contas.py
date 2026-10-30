# contas.py
# Contas dos clientes da loja: cadastro, login (CPF + senha) e "Minha conta"
# com os dados do cliente e o historico de pedidos.
# Projeto: Quilombo Doces

import hashlib
import re
import secrets
import time

from flask import (Blueprint, request, render_template, redirect, url_for,
                   session, flash)
from werkzeug.security import generate_password_hash, check_password_hash

from cadastro_sqlite import conectar_banco
from envio_email import enviar_email

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
    campos = ("nome", "cpf", "email", "telefone", "endereco", "numero",
              "complemento", "bairro", "cidade", "cep")
    dados = {c: request.form.get(c, "").strip() for c in campos}
    dados["email"] = dados["email"].lower()
    return dados


def validar_email(email, conn, id_atual=None):
    """Devolve a mensagem de erro do e-mail, ou "" se estiver tudo certo."""
    # formato simples: algo@algo.algo (sem espacos)
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return "Informe um e-mail válido (ex.: maria@gmail.com)."
    existente = conn.execute(
        'SELECT id FROM clientes WHERE LOWER(email) = ? AND id <> ?',
        (email.lower(), id_atual or 0)).fetchone()
    if existente:
        return "Já existe uma conta com esse e-mail."
    return ""


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

    erro_email = validar_email(dados["email"], conn, id_atual)
    if erro_email:
        erros["email"] = erro_email

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

        'INSERT INTO clientes (nome, cpf, email, telefone, endereco, numero, complemento, '
        'bairro, cidade, cep, senha_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (dados["nome"], so_numeros(dados["cpf"]), dados["email"], dados["telefone"],
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
        'UPDATE clientes SET nome = ?, cpf = ?, email = ?, telefone = ?, endereco = ?, '
        'numero = ?, complemento = ?, bairro = ?, cidade = ?, cep = ? WHERE id = ?',
        (dados["nome"], so_numeros(dados["cpf"]), dados["email"], dados["telefone"],
         dados["endereco"], dados["numero"], dados["complemento"], dados["bairro"],
         dados["cidade"], dados["cep"], cliente["id"]))
    if request.form.get("senha"):
        conn.execute('UPDATE clientes SET senha_hash = ? WHERE id = ?',
                     (generate_password_hash(request.form["senha"]), cliente["id"]))
    conn.commit()
    conn.close()

    flash("Dados atualizados!")
    return redirect(destino_seguro(proximo))


# --------------------------------------------------- E-MAIL OBRIGATORIO
# Contas antigas (criadas antes do campo de e-mail) precisam informar o
# e-mail antes de continuar comprando: sem ele nao da para recuperar a senha.

@contas.before_app_request
def exigir_email():
    """Cliente logado sem e-mail: so libera a loja depois de informar."""
    endpoint = request.endpoint or ""
    if not (endpoint.startswith("loja") or endpoint.startswith("contas.")):
        return None                         # area do admin, arquivos etc.
    if endpoint in ("contas.informar_email", "contas.sair"):
        return None
    cliente = cliente_atual()
    if cliente is not None and not cliente["email"]:
        return redirect(url_for("contas.informar_email", proximo=request.full_path))
    return None


@contas.route("/conta/email", methods=["GET", "POST"])
def informar_email():
    """Aba que pede o e-mail de quem criou a conta antes de ele existir."""
    cliente = cliente_atual()
    if cliente is None:
        return redirect(url_for("contas.entrar"))

    proximo = request.values.get("proximo", "")
    erro = ""
    email = ""

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        conn = conectar_banco()
        erro = validar_email(email, conn, id_atual=cliente["id"])
        if not erro:
            conn.execute('UPDATE clientes SET email = ? WHERE id = ?',
                         (email, cliente["id"]))
            conn.commit()
        conn.close()
        if not erro:
            flash("E-mail salvo! Se esquecer a senha, é para ele que vamos mandar o link.")
            return redirect(destino_seguro(proximo))

    return render_template("conta_email.html", cliente=cliente, email=email,
                           erro=erro, proximo=proximo)


# --------------------------------------------------- ESQUECI MINHA SENHA
# 1. a pessoa digita o e-mail da conta;
# 2. o site manda um link secreto para esse e-mail (vale 1 hora, uma vez so);
# 3. pelo link, ela escolhe uma senha nova.

VALIDADE_LINK = 60 * 60          # 1 hora, em segundos


def hash_token(token):
    """O codigo do link nao fica salvo no banco, so o "hash" dele: mesmo que
    alguem veja o banco, nao consegue montar o link."""
    return hashlib.sha256(token.encode()).hexdigest()


@contas.route("/conta/esqueci", methods=["GET", "POST"])
def esqueci_senha():
    """Pede o e-mail e manda o link para criar uma senha nova."""
    if request.method == "GET":
        return render_template("conta_esqueci.html", enviado=False, email="")

    email = request.form.get("email", "").strip().lower()
    conn = conectar_banco()
    cliente = conn.execute('SELECT * FROM clientes WHERE LOWER(email) = ?',
                           (email,)).fetchone()

    if cliente is not None:
        token = secrets.token_urlsafe(32)        # codigo secreto do link
        # links antigos deste cliente deixam de valer
        conn.execute('UPDATE redefinicoes_senha SET usado = 1 WHERE cliente_id = ?',
                     (cliente["id"],))
        conn.execute(
            'INSERT INTO redefinicoes_senha (cliente_id, token_hash, expira_em) '
            'VALUES (?, ?, ?)',
            (cliente["id"], hash_token(token), time.time() + VALIDADE_LINK))
        conn.commit()

        link = url_for("contas.redefinir_senha", token=token, _external=True)
        primeiro_nome = cliente["nome"].split()[0]
        texto = (f"Olá, {primeiro_nome}!\n\n"
                 "Recebemos um pedido para trocar a senha da sua conta na Quilombo Doces.\n"
                 f"Para criar uma senha nova, abra este link (vale por 1 hora):\n\n{link}\n\n"
                 "Se não foi você, é só ignorar este e-mail: sua senha continua a mesma.\n\n"
                 "Quilombo Doces")
        html = render_template("email_redefinir.html", nome=primeiro_nome, link=link)
        enviar_email(cliente["email"], "Quilombo Doces - criar uma nova senha", texto, html)
    conn.close()

    # a mesma resposta tendo conta ou nao: assim ninguem descobre quais
    # e-mails estao cadastrados
    return render_template("conta_esqueci.html", enviado=True, email=email)


def buscar_redefinicao(conn, token):
    """O pedido de troca de senha deste link, se ainda valer (senao None)."""
    return conn.execute(
        'SELECT * FROM redefinicoes_senha WHERE token_hash = ? AND usado = 0 '
        'AND expira_em > ?', (hash_token(token), time.time())).fetchone()


@contas.route("/conta/redefinir/<token>", methods=["GET", "POST"])
def redefinir_senha(token):
    """Pagina do link do e-mail: escolher a senha nova."""
    conn = conectar_banco()
    pedido = buscar_redefinicao(conn, token)
    if pedido is None:
        conn.close()
        return render_template("conta_redefinir.html", valido=False, erro="")

    erro = ""
    if request.method == "POST":
        senha = request.form.get("senha", "")
        if len(senha) < 6:
            erro = "A senha precisa ter pelo menos 6 caracteres."
        elif senha != request.form.get("confirmar", ""):
            erro = "As duas senhas não são iguais."
        else:
            conn.execute('UPDATE clientes SET senha_hash = ? WHERE id = ?',
                         (generate_password_hash(senha), pedido["cliente_id"]))
            conn.execute('UPDATE redefinicoes_senha SET usado = 1 WHERE cliente_id = ?',
                         (pedido["cliente_id"],))
            conn.commit()
            conn.close()
            flash("Senha trocada! Agora entre com o seu CPF e a senha nova.")
            return redirect(url_for("contas.entrar"))

    conn.close()
    return render_template("conta_redefinir.html", valido=True, erro=erro, token=token)


@contas.route("/conta/sair", methods=["POST"])
def sair():
    session.pop("cliente_id", None)
    flash("Você saiu da sua conta.")
    return redirect(url_for("loja"))