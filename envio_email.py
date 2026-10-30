# envio_email.py
# Envia e-mails do site (por enquanto: o link do "Esqueci minha senha").
# Usa uma conta do Gmail com "senha de app" (veja config_email_exemplo.py).
# Projeto: Quilombo Doces

import os
import smtplib
from email.message import EmailMessage

# a conta que envia: primeiro procura nas variaveis de ambiente (servidor),
# depois no arquivo config_email.py (seu computador; nao vai para o GitHub)
try:
    import config_email
except ImportError:
    config_email = None

REMETENTE = os.environ.get("EMAIL_REMETENTE") or getattr(config_email, "EMAIL_REMETENTE", "")
SENHA_APP = os.environ.get("EMAIL_SENHA_APP") or getattr(config_email, "EMAIL_SENHA_APP", "")


def email_configurado():
    """True se ja tem uma conta de e-mail configurada para enviar."""
    return bool(REMETENTE and SENHA_APP)


def enviar_email(para, assunto, texto, html=None):
    """Envia um e-mail. Devolve True se enviou.

    Sem conta configurada (ou se der erro), nao envia: mostra o e-mail no
    terminal do VS Code, assim da para testar no seu computador."""
    if not email_configurado():
        print("\n===== E-MAIL (nao enviado: configure o config_email.py) =====")
        print(f"Para: {para}\nAssunto: {assunto}\n\n{texto}")
        print("=============================================================\n")
        return False

    msg = EmailMessage()
    msg["From"] = f"Quilombo Doces <{REMETENTE}>"
    msg["To"] = para
    msg["Subject"] = assunto
    msg.set_content(texto)                    # versao so texto
    if html:
        msg.add_alternative(html, subtype="html")   # versao bonita

    senha = SENHA_APP.replace(" ", "")
    try:
        # Gmail, jeito 1: porta 587 (a conexao vira segura com STARTTLS).
        # E a que menos e bloqueada por redes de escola/empresa e antivirus.
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as servidor:
            servidor.starttls()
            servidor.login(REMETENTE, senha)
            servidor.send_message(msg)
        return True
    except smtplib.SMTPAuthenticationError as erro:
        print(f"[envio_email] O Gmail recusou o e-mail/senha de app: {erro}")
    except (smtplib.SMTPException, OSError) as erro:
        print(f"[envio_email] Porta 587 nao funcionou ({erro}); tentando a 465...")
        try:
            # Gmail, jeito 2: porta 465 com conexao segura (SSL) desde o inicio
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as servidor:
                servidor.login(REMETENTE, senha)
                servidor.send_message(msg)
            return True
        except (smtplib.SMTPException, OSError) as erro2:
            print(f"[envio_email] Nao foi possivel enviar para {para}: {erro2}")

    print(texto)        # nao enviou: mostra o e-mail (com o link) no terminal
    return False
