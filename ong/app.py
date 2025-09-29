import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, session, g
from werkzeug.security import generate_password_hash, check_password_hash
import os

# Configurações básicas
APP_SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'troque_esta_chave_para_producao')  # troque em produção
ADMIN_USERNAME = os.environ.get('ADMIN_USER', 'admin')
# Senha padrão: 'senha123' — Mude usando variável de ambiente ADMIN_PASS ou altere aqui.
DEFAULT_ADMIN_PASSWORD = os.environ.get('ADMIN_PASS', 'senha123')

app = Flask(__name__)
app.config['SECRET_KEY'] = APP_SECRET_KEY
DATABASE = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'database.db')

# Armazenamos o hash da senha no runtime
ADMIN_PASSWORD_HASH = generate_password_hash(DEFAULT_ADMIN_PASSWORD)


# ----------- Banco de Dados -----------

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


def init_db():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS interessados (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      nome TEXT NOT NULL,
      email TEXT NOT NULL,
      tipo TEXT NOT NULL,
      mensagem TEXT,
      data_envio DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)
    db.commit()


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


# ----------- Rotas -----------

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        email = request.form.get('email', '').strip()
        tipo = request.form.get('tipo', '').strip()
        mensagem = request.form.get('mensagem', '').strip()

        # Validação mínima
        if not nome or not email or not tipo:
            flash('Por favor preencha Nome, E-mail e Tipo de interesse.', 'danger')
            return redirect(url_for('index'))

        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO interessados (nome, email, tipo, mensagem) VALUES (?, ?, ?, ?)",
            (nome, email, tipo, mensagem)
        )
        db.commit()
        flash('Obrigado! Seu interesse foi registrado.', 'success')
        return redirect(url_for('index'))

    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'admin_logged' in session and session['admin_logged']:
        return redirect(url_for('admin'))

    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')

        if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session['admin_logged'] = True
            session['admin_user'] = username
            flash('Login efetuado com sucesso.', 'success')
            return redirect(url_for('admin'))
        else:
            flash('Usuário ou senha incorretos.', 'danger')
            return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('admin_logged', None)
    session.pop('admin_user', None)
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('login'))


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged'):
            flash('Acesso restrito. Faça login.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/admin')
@login_required
def admin():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM interessados ORDER BY data_envio DESC")
    entries = cursor.fetchall()
    return render_template('admin.html', entries=entries)


@app.route('/delete/<int:entry_id>', methods=['POST'])
@login_required
def delete_entry(entry_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM interessados WHERE id = ?", (entry_id,))
    db.commit()
    flash('Registro excluído.', 'success')
    return redirect(url_for('admin'))


# Exportar CSV
@app.route('/export.csv')
@login_required
def export_csv():
    import csv
    from io import StringIO
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, nome, email, tipo, mensagem, data_envio FROM interessados ORDER BY data_envio DESC")
    rows = cursor.fetchall()

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['id', 'nome', 'email', 'tipo', 'mensagem', 'data_envio'])
    for r in rows:
        cw.writerow([r['id'], r['nome'], r['email'], r['tipo'], r['mensagem'], r['data_envio']])
    output = si.getvalue()
    from flask import Response
    return Response(output, mimetype="text/csv", headers={"Content-Disposition":"attachment;filename=interessados.csv"})


# ----------- Main -----------

if __name__ == '__main__':
    # Inicializa o banco logo no início (compatível com Flask 3.x)
    with app.app_context():
        init_db()

    # Modo debug facilita a apresentação
    app.run(debug=True)
