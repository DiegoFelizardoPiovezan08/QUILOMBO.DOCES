# app.py
# Aplicacao web com Flask — CRUD completo de doces pelo navegador
# Projeto: Quilombo Doces

import os
import uuid

from flask import (Flask, request, render_template, redirect, url_for,
                   session, flash)
from cadastro_sqlite import conectar_banco, validar_preco
from urllib.parse import quote


app = Flask(__name__)


app.secret_key = "Neymar"
WHATSAPP = "5511998325340"  # seu número com DDI + DDD

# --------------------------------------------------------------- IMAGENS

# as fotos enviadas ficam em static/uploads (a pasta e criada sozinha)
PASTA_UPLOADS = os.path.join(app.root_path, "static", "uploads")
EXTENSOES_IMAGEM = {"png", "jpg", "jpeg", "gif", "webp"}
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024   # limite: 5 MB por envio


def ler_imagem(campo="imagem"):
    """Le a foto enviada no formulario.

    Devolve (arquivo, erro). arquivo e None quando nada foi enviado.
    """
    arquivo = request.files.get(campo)
    if arquivo is None or arquivo.filename == "":
        return None, None

    extensao = arquivo.filename.rsplit(".", 1)[-1].lower()
    if "." not in arquivo.filename or extensao not in EXTENSOES_IMAGEM:
        return None, "Envie uma imagem JPG, PNG, GIF ou WEBP."

    return arquivo, None


def salvar_imagem(arquivo):
    """Grava a foto em static/uploads com um nome unico e devolve esse nome."""
    os.makedirs(PASTA_UPLOADS, exist_ok=True)
    extensao = arquivo.filename.rsplit(".", 1)[-1].lower()
    nome = f"{uuid.uuid4().hex}.{extensao}"
    arquivo.save(os.path.join(PASTA_UPLOADS, nome))
    return nome


def apagar_imagem(nome):
    """Apaga a foto antiga (quando o registro e excluido ou a foto trocada)."""
    if nome:
        caminho = os.path.join(PASTA_UPLOADS, nome)
        if os.path.exists(caminho):
            os.remove(caminho)


# --------------------------------------------------------------- LEITURA (GET)

@app.route("/")
def listar():
    """Pagina inicial: todos os doces cadastrados."""
    conn = conectar_banco()
    doces = conn.execute(
        'SELECT * FROM doces ORDER BY nome').fetchall()
    conn.close()

    #a mensagem de sucesso chega pela URL, apos o redirect
    return render_template("lista.html", doces=doces,
                           msg=request.args.get("msg", ""))


@app.route("/doce/<int:id_doce>")
def detalhe(id_doce):
    """Pagina de um doce especifico."""
    conn = conectar_banco()
    doce = conn.execute('SELECT * FROM doces WHERE id = ?',
                        (id_doce,)).fetchone()
    conn.close()

    if doce is None:
        return render_template("erro.html",
                               mensagem=f"Nao existe doce com id {id_doce}."), 404

    return render_template("detalhe.html", doce=doce)


@app.route("/buscar")
def buscar():
    """Busca por nome. O termo vem na URL: /buscar?termo=brigadeiro"""
    termo = request.args.get("termo", "").strip().lower()

    encontrados = []
    if termo:
        conn = conectar_banco()
        encontrados = conn.execute(
            'SELECT * FROM doces WHERE LOWER(nome) LIKE ? ORDER BY nome',
            (f'%{termo}%',)
        ).fetchall()
        conn.close()

    return render_template("busca.html", termo=termo, doces=encontrados)





# --------------------------------------------------------------- VALIDACAO

def validar_formulario(dados, conn, id_atual=None):
    """Valida os dados vindos do formulario.

    Devolve um dicionario de erros: {campo: mensagem}.
    Dicionario vazio significa que esta tudo certo.
    """
    erros = {}

    if len(dados["nome"]) < 2:
        erros["nome"] = "O nome deve ter pelo menos 2 caracteres."
    else:
        # regra que depende do banco: o nome do doce nao pode se repetir.
        # Ao EDITAR, o proprio registro nao conta como duplicata.
        if id_atual is None:
            existente = conn.execute(
                'SELECT id FROM doces WHERE LOWER(nome) = ?',
                (dados["nome"].lower(),)).fetchone()
        else:
            existente = conn.execute(
                'SELECT id FROM doces WHERE LOWER(nome) = ? AND id <> ?',
                (dados["nome"].lower(), id_atual)).fetchone()
        if existente:
            erros["nome"] = "Ja existe um doce com esse nome."

    if not validar_preco(dados["preco"]):
        erros["preco"] = "Informe um preco valido, maior que zero (exemplo: 18,50)."

    return erros


def ler_formulario():
    """Le os campos enviados e devolve um dicionario ja limpo."""
    return {
        "nome": request.form.get("nome", "").strip(),
        "preco": request.form.get("preco", "").strip(),
    }


# --------------------------------------------------------------- CADASTRAR

@app.route("/novo", methods=["GET", "POST"])
def novo():
    """GET exibe o formulario; POST grava o doce."""
    if request.method == "GET":
        return render_template("form.html", titulo="Cadastrar doce",
                               dados={}, erros={}, acao=url_for("novo"))

    dados = ler_formulario()

    conn = conectar_banco()
    erros = validar_formulario(dados, conn)
    arquivo, erro_imagem = ler_imagem()
    if erro_imagem:
        erros["imagem"] = erro_imagem

    if erros:
        conn.close()
        # devolve o formulario COM o que foi digitado e as mensagens
        return render_template("form.html", titulo="Cadastrar doce",
                               dados=dados, erros=erros,
                               acao=url_for("novo")), 400

    imagem = salvar_imagem(arquivo) if arquivo else None

    conn.execute(
        'INSERT INTO doces (nome, preco, imagem) VALUES (?, ?, ?)',
        (dados["nome"].title(),
         round(float(dados["preco"].replace(",", ".")), 2),
         imagem))
    conn.commit()
    conn.close()

    # POST-Redirect-GET: nunca devolver a pagina direto depois de gravar
    return redirect(url_for("listar", msg="Doce cadastrado com sucesso!"))


# --------------------------------------------------------------- EDITAR

@app.route("/doce/<int:id_doce>/editar", methods=["GET", "POST"])
def editar(id_doce):
    """GET exibe o formulario preenchido; POST grava a alteracao."""
    conn = conectar_banco()
    doce = conn.execute('SELECT * FROM doces WHERE id = ?',
                        (id_doce,)).fetchone()

    if doce is None:
        conn.close()
        return render_template("erro.html",
                               mensagem=f"Nao existe doce com id {id_doce}."), 404

    if request.method == "GET":
        conn.close()
        # dict(doce) converte a linha do banco em dicionario
        dados = dict(doce)
        dados["preco"] = f"{doce['preco']:.2f}".replace(".", ",")
        return render_template("form.html", titulo=f"Editar {doce['nome']}",
                               dados=dados, erros={},
                               acao=url_for("editar", id_doce=id_doce))

    dados = ler_formulario()
    dados["imagem"] = doce["imagem"]     # para o formulario mostrar a foto atual
    erros = validar_formulario(dados, conn, id_atual=id_doce)
    arquivo, erro_imagem = ler_imagem()
    if erro_imagem:
        erros["imagem"] = erro_imagem

    if erros:
        conn.close()
        return render_template("form.html", titulo=f"Editar {doce['nome']}",
                               dados=dados, erros=erros,
                               acao=url_for("editar", id_doce=id_doce)), 400

    # foto: troca se veio uma nova, apaga se marcou "remover", senao mantem
    imagem = doce["imagem"]
    if arquivo:
        apagar_imagem(imagem)
        imagem = salvar_imagem(arquivo)
    elif request.form.get("remover_imagem"):
        apagar_imagem(imagem)
        imagem = None

    conn.execute(
        'UPDATE doces SET nome = ?, preco = ?, imagem = ? WHERE id = ?',
        (dados["nome"].title(),
         round(float(dados["preco"].replace(",", ".")), 2),
         imagem,
         id_doce))
    conn.commit()
    conn.close()

    return redirect(url_for("listar", msg="Dados atualizados com sucesso!"))


# --------------------------------------------------------------- EXCLUIR

@app.route("/doce/<int:id_doce>/excluir", methods=["POST"])
def excluir(id_doce):
    """Exclui o doce. Aceita SOMENTE POST — um link nao pode apagar dados."""
    conn = conectar_banco()
    doce = conn.execute('SELECT * FROM doces WHERE id = ?',
                        (id_doce,)).fetchone()

    if doce is None:
        conn.close()
        return render_template("erro.html",
                               mensagem=f"Nao existe doce com id {id_doce}."), 404

    conn.execute('DELETE FROM doces WHERE id = ?', (id_doce,))
    conn.commit()
    conn.close()
    apagar_imagem(doce["imagem"])

    return redirect(url_for("listar",
                            msg=f"Registro de {doce['nome']} excluido."))


@app.errorhandler(404)
def pagina_nao_encontrada(erro):
    return render_template("erro.html",
                           mensagem="Confira o endereco digitado."), 404


@app.errorhandler(413)
def arquivo_grande(erro):
    return render_template("erro.html", titulo="Arquivo muito grande",
                           mensagem="A imagem deve ter no maximo 5 MB."), 413



# --------------------------------------------------------------- CARRINHO

@app.route("/carrinho/adicionar/<int:id>", methods=["POST"])
def adicionar_carrinho(id):
    carrinho = session.get("carrinho", {})
    chave = str(id)
    carrinho[chave] = carrinho.get(chave, 0) + 1
    session["carrinho"] = carrinho
    return redirect(request.referrer or url_for("carrinho"))


@app.route("/carrinho")
def carrinho():
    itens = []
    total = 0

    conn = conectar_banco()
    for chave, qtd in session.get("carrinho", {}).items():
        doce = conn.execute('SELECT * FROM doces WHERE id = ?',
                            (int(chave),)).fetchone()
        if doce is None:      # doce foi excluído depois de entrar no carrinho
            continue
        subtotal = doce["preco"] * qtd
        total += subtotal
        itens.append({"id": doce["id"], "nome": doce["nome"],
                      "preco": doce["preco"], "qtd": qtd, "subtotal": subtotal})
    conn.close()

    linhas = ["Olá! Gostaria de fazer este pedido:"]
    for i in itens:
        linhas.append(f"- {i['qtd']}x {i['nome']} (R$ {i['subtotal']:.2f})")
    linhas.append(f"Total: R$ {total:.2f}")
    link_whatsapp = f"https://wa.me/{WHATSAPP}?text={quote(chr(10).join(linhas))}"

    return render_template("carrinho.html", itens=itens, total=total,
                           link_whatsapp=link_whatsapp)


@app.route("/carrinho/remover/<int:id>", methods=["POST"])
def remover_carrinho(id):
    carrinho = session.get("carrinho", {})
    carrinho.pop(str(id), None)
    session["carrinho"] = carrinho
    return redirect(url_for("carrinho"))


@app.route("/carrinho/limpar", methods=["POST"])
def limpar_carrinho():
    session.pop("carrinho", None)
    return redirect(url_for("carrinho"))


@app.template_filter("brl")
def formato_brl(valor):
    """Mostra 18.5 como 18,50 (usado nos templates: {{ preco|brl }})."""
    return f"{float(valor):.2f}".replace(".", ",")


@app.context_processor
def dados_globais():
    """Variaveis disponiveis em TODOS os templates."""
    return {
        "qtd_carrinho": sum(session.get("carrinho", {}).values()),
        "whatsapp": WHATSAPP,
    }


def montar_carrinho():
    """Le o carrinho da sessao e devolve (itens, total, link_whatsapp)."""
    itens = []
    total = 0

    conn = conectar_banco()
    for chave, qtd in session.get("carrinho", {}).items():
        doce = conn.execute('SELECT * FROM doces WHERE id = ?',
                            (int(chave),)).fetchone()
        if doce is None:          # doce excluido depois de entrar no carrinho
            continue
        subtotal = doce["preco"] * qtd
        total += subtotal
        itens.append({"id": doce["id"], "nome": doce["nome"],
                      "preco": doce["preco"], "qtd": qtd,
                      "subtotal": subtotal, "imagem": doce["imagem"]})
    conn.close()

    linhas = ["Olá! Gostaria de fazer este pedido:"]
    for i in itens:
        linhas.append(f"- {i['qtd']}x {i['nome']} (R$ {i['subtotal']:.2f})")
    linhas.append(f"Total: R$ {total:.2f}")
    link = f"https://wa.me/{WHATSAPP}?text={quote(chr(10).join(linhas))}"

    return itens, total, link


# ----------------------------------------------------------- VITRINE

@app.route("/loja")
def loja():
    """Pagina inicial da loja: carrossel e destaques."""
    conn = conectar_banco()
    # cada foto vira {"arquivo": caminho dentro de static, "legenda": texto}
    slides = [{"arquivo": "uploads/" + s["imagem"], "legenda": s["legenda"]}
              for s in conn.execute('SELECT * FROM carrossel ORDER BY id')]
    doces = conn.execute('SELECT * FROM doces ORDER BY nome LIMIT 4').fetchall()
    conn.close()

    # nenhuma foto cadastrada na aba Carrossel: usa as fotos de static/img
    # (carrossel-1.jpg ate carrossel-4.jpg), se existirem
    if not slides:
        for n in range(1, 5):
            arquivo = f"img/carrossel-{n}.jpg"
            if os.path.exists(os.path.join(app.static_folder, arquivo)):
                slides.append({"arquivo": arquivo, "legenda": ""})

    return render_template("loja.html", slides=slides, doces=doces)


@app.route("/loja/produtos")
def loja_produtos():
    """Botao "Produtos": todos os doces, ou o resultado de uma busca."""
    termo = request.args.get("termo", "").strip().lower()

    conn = conectar_banco()
    if termo:
        doces = conn.execute(
            'SELECT * FROM doces WHERE LOWER(nome) LIKE ? ORDER BY nome',
            (f'%{termo}%',)).fetchall()
    else:
        doces = conn.execute('SELECT * FROM doces ORDER BY nome').fetchall()
    conn.close()

    return render_template("loja_produtos.html", doces=doces, termo=termo)


@app.route("/loja/doce/<int:id_doce>")
def loja_produto(id_doce):
    """Pagina de um doce para o consumidor."""
    conn = conectar_banco()
    doce = conn.execute('SELECT * FROM doces WHERE id = ?',
                        (id_doce,)).fetchone()
    conn.close()

    if doce is None:
        return render_template("erro.html",
                               mensagem=f"Nao existe doce com id {id_doce}."), 404

    return render_template("loja_produto.html", doce=doce)


@app.route("/loja/eventos")
def loja_eventos():
    """Botao "Eventos": todos os eventos para o consumidor."""
    conn = conectar_banco()
    eventos = conn.execute('SELECT * FROM eventos ORDER BY nome').fetchall()
    conn.close()

    return render_template("loja_eventos.html", eventos=eventos)


@app.route("/loja/evento/<int:id_evento>")
def loja_evento(id_evento):
    """Pagina de um evento para o consumidor."""
    conn = conectar_banco()
    evento = conn.execute('SELECT * FROM eventos WHERE id = ?',
                          (id_evento,)).fetchone()
    conn.close()

    if evento is None:
        return render_template("erro.html",
                               mensagem=f"Nao existe evento com id {id_evento}."), 404

    texto = f"Olá! Tenho interesse no evento: {evento['nome']}"
    link_whatsapp = f"https://wa.me/{WHATSAPP}?text={quote(texto)}"

    return render_template("loja_evento.html", evento=evento,
                           link_whatsapp=link_whatsapp)


@app.route("/loja/sobre")
def loja_sobre():
    """Botao "Sobre": a historia da loja para o consumidor."""
    conn = conectar_banco()
    sobre = conn.execute('SELECT * FROM sobre ORDER BY id LIMIT 1').fetchone()
    conn.close()

    return render_template("loja_sobre.html", sobre=sobre)


# ----------------------------------------------------------- CARRINHO

@app.route("/loja/carrinho")
def loja_carrinho():
    itens, total, link_whatsapp = montar_carrinho()
    return render_template("loja_carrinho.html", itens=itens, total=total,
                           link_whatsapp=link_whatsapp)



@app.route("/loja/carrinho/adicionar/<int:id_doce>", methods=["POST"])
def loja_adicionar(id_doce):
    conn = conectar_banco()
    doce = conn.execute('SELECT * FROM doces WHERE id = ?',
                        (id_doce,)).fetchone()
    conn.close()

    if doce is None:
        return render_template("erro.html",
                               mensagem=f"Nao existe doce com id {id_doce}."), 404

    # quantidade vem do campo da pagina do produto (na vitrine nao tem: vale 1)
    try:
        qtd = int(request.form.get("quantidade", "1"))
    except ValueError:
        qtd = 1
    qtd = max(1, min(qtd, 99))

    carrinho = session.get("carrinho", {})
    chave = str(id_doce)
    carrinho[chave] = carrinho.get(chave, 0) + qtd
    session["carrinho"] = carrinho

    flash(f"{doce['nome']} adicionado ao carrinho!")
    return redirect(request.referrer or url_for("loja"))


@app.route("/loja/carrinho/atualizar/<int:id_doce>", methods=["POST"])
def loja_atualizar(id_doce):
    """Botoes de + e - no carrinho."""
    carrinho = session.get("carrinho", {})
    chave = str(id_doce)

    if chave in carrinho:
        if request.form.get("acao") == "mais":
            carrinho[chave] = min(carrinho[chave] + 1, 99)
        else:
            carrinho[chave] -= 1
        if carrinho[chave] <= 0:      # chegou a zero: tira do carrinho
            carrinho.pop(chave)

    session["carrinho"] = carrinho
    return redirect(url_for("loja_carrinho"))


@app.route("/loja/carrinho/remover/<int:id_doce>", methods=["POST"])
def loja_remover(id_doce):
    carrinho = session.get("carrinho", {})
    carrinho.pop(str(id_doce), None)
    session["carrinho"] = carrinho
    return redirect(url_for("loja_carrinho"))


@app.route("/loja/carrinho/limpar", methods=["POST"])
def loja_limpar():
    session.pop("carrinho", None)
    return redirect(url_for("loja_carrinho"))

# ----------------------------------------------------------- EVENTOS

@app.route("/eventos")
def eventos():  
    """Pagina inicial: todos os eventos cadastrados."""
    conn = conectar_banco()
    eventos = conn.execute(
        'SELECT * FROM eventos ORDER BY nome').fetchall()
    conn.close()

    #a mensagem de sucesso chega pela URL, apos o redirect
    return render_template("eventos.html", eventos=eventos,
                           msg=request.args.get("msg", "")) 

@app.route("/novo_evento", methods=["GET", "POST"])
def novo_evento():
    """GET exibe o formulario; POST grava o evento."""
    if request.method == "GET":
        return render_template("form_evento.html", titulo="Cadastrar evento",
                               dados={}, erros={}, acao=url_for("novo_evento"))

    dados = {
        "nome": request.form.get("nome", "").strip(),
        "descricao": request.form.get("descricao", "").strip(),
    }

    conn = conectar_banco()
    erros = {}
    if len(dados["nome"]) < 2:
        erros["nome"] = "O nome deve ter pelo menos 2 caracteres."
    arquivo, erro_imagem = ler_imagem()
    if erro_imagem:
        erros["imagem"] = erro_imagem

    if erros:
        conn.close()
        return render_template("form_evento.html", titulo="Cadastrar evento",
                               dados=dados, erros=erros,
                               acao=url_for("novo_evento")), 400

    imagem = salvar_imagem(arquivo) if arquivo else None

    conn.execute(
        'INSERT INTO eventos (nome, descricao, imagem) VALUES (?, ?, ?)',
        (dados["nome"].title(), dados["descricao"], imagem))
    conn.commit()
    conn.close()

    return redirect(url_for("eventos", msg="Evento cadastrado com sucesso!"))

@app.route("/evento/<int:id_evento>/editar", methods=["GET", "POST"])
def editar_evento(id_evento):       
    """GET exibe o formulario preenchido; POST grava a alteracao."""
    conn = conectar_banco()
    evento = conn.execute('SELECT * FROM eventos WHERE id = ?',
                        (id_evento,)).fetchone()

    if evento is None:
        conn.close()
        return render_template("erro.html",
                               mensagem=f"Nao existe evento com id {id_evento}."), 404

    if request.method == "GET":
        conn.close()
        dados = dict(evento)
        return render_template("form_evento.html", titulo=f"Editar {evento['nome']}",
                               dados=dados, erros={},
                               acao=url_for("editar_evento", id_evento=id_evento))

    dados = {
        "nome": request.form.get("nome", "").strip(),
        "descricao": request.form.get("descricao", "").strip(),
        "imagem": evento["imagem"],
    }
    erros = {}
    if len(dados["nome"]) < 2:
        erros["nome"] = "O nome deve ter pelo menos 2 caracteres."
    arquivo, erro_imagem = ler_imagem()
    if erro_imagem:
        erros["imagem"] = erro_imagem

    if erros:
        conn.close()
        return render_template("form_evento.html", titulo=f"Editar {evento['nome']}",
                               dados=dados, erros=erros,
                               acao=url_for("editar_evento", id_evento=id_evento)), 400

    imagem = evento["imagem"]
    if arquivo:
        apagar_imagem(imagem)
        imagem = salvar_imagem(arquivo)
    elif request.form.get("remover_imagem"):
        apagar_imagem(imagem)
        imagem = None

    conn.execute(
        'UPDATE eventos SET nome = ?, descricao = ?, imagem = ? WHERE id = ?',
        (dados["nome"].title(), dados["descricao"], imagem, id_evento))
    conn.commit()
    conn.close()

    return redirect(url_for("eventos", msg="Dados do evento atualizados com sucesso!"))

@app.route("/evento/<int:id_evento>/excluir", methods=["POST"])
def excluir_evento(id_evento):
    """Exclui o evento. Aceita SOMENTE POST — um link nao pode apagar dados."""
    conn = conectar_banco()
    evento = conn.execute('SELECT * FROM eventos WHERE id = ?',
                        (id_evento,)).fetchone()

    if evento is None:
        conn.close()
        return render_template("erro.html",
                               mensagem=f"Nao existe evento com id {id_evento}."), 404

    conn.execute('DELETE FROM eventos WHERE id = ?', (id_evento,))
    conn.commit()
    conn.close()
    apagar_imagem(evento["imagem"])

    return redirect(url_for("eventos",
                            msg=f"Registro de {evento['nome']} excluido."))

# ----------------------------------------------------------- SOBRE

@app.route("/sobre", methods=["GET", "POST"])
def sobre():
    """Pagina "Sobre" da loja: UMA foto e o texto embaixo.

    GET mostra o formulario ja preenchido; POST grava (cria na primeira vez,
    depois so atualiza o mesmo registro).
    """
    conn = conectar_banco()
    atual = conn.execute('SELECT * FROM sobre ORDER BY id LIMIT 1').fetchone()

    if request.method == "GET":
        conn.close()
        return render_template("sobre.html", dados=dict(atual) if atual else {},
                               erros={}, msg=request.args.get("msg", ""))

    dados = {
        "titulo": request.form.get("titulo", "").strip(),
        "texto": request.form.get("texto", "").strip(),
        "imagem": atual["imagem"] if atual else None,
    }
    arquivo, erro_imagem = ler_imagem()

    # foto: troca se veio uma nova, apaga se marcou "remover", senao mantem
    imagem = dados["imagem"]
    if request.form.get("remover_imagem") and arquivo is None:
        imagem = None

    erros = {}
    if erro_imagem:
        erros["imagem"] = erro_imagem
    elif not dados["texto"] and arquivo is None and imagem is None:
        erros["texto"] = "Escreva um texto ou envie uma foto."

    if erros:
        conn.close()
        return render_template("sobre.html", dados=dados, erros=erros, msg=""), 400

    if arquivo:
        apagar_imagem(dados["imagem"])
        imagem = salvar_imagem(arquivo)
    elif imagem is None:
        apagar_imagem(dados["imagem"])

    if atual:
        conn.execute('UPDATE sobre SET titulo = ?, texto = ?, imagem = ? WHERE id = ?',
                     (dados["titulo"], dados["texto"], imagem, atual["id"]))
        # se ficaram blocos da versao antiga (varios blocos), apaga os extras
        for extra in conn.execute('SELECT * FROM sobre WHERE id <> ?',
                                  (atual["id"],)).fetchall():
            apagar_imagem(extra["imagem"])
        conn.execute('DELETE FROM sobre WHERE id <> ?', (atual["id"],))
    else:
        conn.execute('INSERT INTO sobre (titulo, texto, imagem) VALUES (?, ?, ?)',
                     (dados["titulo"], dados["texto"], imagem))
    conn.commit()
    conn.close()

    return redirect(url_for("sobre", msg="Página Sobre salva com sucesso!"))



# ----------------------------------------------------------- CARROSSEL

@app.route("/carrossel", methods=["GET", "POST"])
def carrossel():
    """GET mostra as fotos do carrossel; POST adiciona uma foto nova."""
    conn = conectar_banco()
    erros = {}

    if request.method == "POST":
        arquivo, erro_imagem = ler_imagem()
        if arquivo is None and erro_imagem is None:
            erro_imagem = "Escolha uma imagem para enviar."

        if erro_imagem:
            erros["imagem"] = erro_imagem
        else:
            conn.execute(
                'INSERT INTO carrossel (imagem, legenda) VALUES (?, ?)',
                (salvar_imagem(arquivo), request.form.get("legenda", "").strip()))
            conn.commit()
            conn.close()
            return redirect(url_for("carrossel", msg="Foto adicionada ao carrossel!"))

    slides = conn.execute('SELECT * FROM carrossel ORDER BY id').fetchall()
    conn.close()

    return render_template("carrossel.html", slides=slides, erros=erros,
                           msg=request.args.get("msg", "")), (400 if erros else 200)


@app.route("/carrossel/<int:id_slide>/excluir", methods=["POST"])
def excluir_slide(id_slide):
    """Tira uma foto do carrossel e apaga o arquivo."""
    conn = conectar_banco()
    slide = conn.execute('SELECT * FROM carrossel WHERE id = ?',
                         (id_slide,)).fetchone()

    if slide is None:
        conn.close()
        return render_template("erro.html",
                               mensagem=f"Nao existe foto com id {id_slide}."), 404

    conn.execute('DELETE FROM carrossel WHERE id = ?', (id_slide,))
    conn.commit()
    conn.close()
    apagar_imagem(slide["imagem"])

    return redirect(url_for("carrossel", msg="Foto removida do carrossel."))


if __name__ == "__main__":
    app.run(debug=True)