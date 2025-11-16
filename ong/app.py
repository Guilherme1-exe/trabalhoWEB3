import sqlite3
import os
import csv
from io import StringIO
from flask import Flask, render_template, request, redirect, url_for, flash, session, g, Response
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import logging # Para debug
import re # Para criar "slugs"

# Configurações básicas
APP_SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'troque_esta_chave_para_producao')
ADMIN_USERNAME = os.environ.get('ADMIN_USER', 'admin')
DEFAULT_ADMIN_PASSWORD = os.environ.get('ADMIN_PASS', 'senha123')

app = Flask(__name__)
app.config['SECRET_KEY'] = APP_SECRET_KEY
DATABASE = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'database.db')

# Configuração da pasta de UPLOAD
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['UPLOAD_FOLDER_PROJETOS'] = os.path.join(UPLOAD_FOLDER, 'projetos')
app.config['UPLOAD_FOLDER_CUSTOM'] = os.path.join(UPLOAD_FOLDER, 'custom') 
app.config['UPLOAD_FOLDER_GALLERY'] = os.path.join(UPLOAD_FOLDER, 'gallery') # NOVO: Pasta para Galeria
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

ADMIN_PASSWORD_HASH = generate_password_hash(DEFAULT_ADMIN_PASSWORD)

# --- VALORES PADRÃO (para a tabela 'config') ---
DEFAULT_SOBRE_TEXTO = "Em 2024 nos tornamos ONG, com 6 membros colaboradores em 5 atividades..."
DEFAULT_SOBRE_IMAGEM_FILENAME = None
DEFAULT_BACKGROUND_IMAGE_FILENAME = None


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# NOVO: Função para criar "slugs" (links amigáveis)
def slugify(s):
    # Remove acentos
    s = re.sub(r'[áàâãä]', 'a', s)
    s = re.sub(r'[éèêë]', 'e', s)
    s = re.sub(r'[íìîï]', 'i', s)
    s = re.sub(r'[óòôõö]', 'o', s)
    s = re.sub(r'[úùûü]', 'u', s)
    s = re.sub(r'[ç]', 'c', s)
    s = s.lower()
    # Remove caracteres especiais
    s = re.sub(r'[^a-z0-9\s-]', '', s).strip()
    # Substitui espaços por hífens
    s = re.sub(r'[\s-]+', '-', s)
    return s


# ----------- Banco de Dados -----------

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


def init_db():
    # Cria as pastas de uploads se não existirem
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['UPLOAD_FOLDER_PROJETOS'], exist_ok=True)
    os.makedirs(app.config['UPLOAD_FOLDER_CUSTOM'], exist_ok=True) 
    os.makedirs(app.config['UPLOAD_FOLDER_GALLERY'], exist_ok=True) # NOVO

    db = get_db()
    cursor = db.cursor()
    
    # Tabela 1: Interessados
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
    
    # Tabela 2: Projetos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS projetos (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      titulo TEXT NOT NULL,
      descricao TEXT NOT NULL,
      imagem_filename TEXT NOT NULL,
      data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP,
      lider_membro_id INTEGER,
      FOREIGN KEY (lider_membro_id) REFERENCES membros(id)
    );
    """)

    # Tabela 3: Membros
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS membros (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      nome TEXT NOT NULL,
      email TEXT NOT NULL UNIQUE
    );
    """)
    
    # Tabela 4: Tabela de Junção (Membros <-> Projetos)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS projetos_membros (
      projeto_id INTEGER,
      membro_id INTEGER,
      PRIMARY KEY (projeto_id, membro_id),
      FOREIGN KEY (projeto_id) REFERENCES projetos(id) ON DELETE CASCADE,
      FOREIGN KEY (membro_id) REFERENCES membros(id) ON DELETE CASCADE
    );
    """)

    # Tabela 5: Config
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS config (
      key TEXT PRIMARY KEY,
      value TEXT
    );
    """)
    
    # Tabela 6: Seções Personalizadas
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS custom_sections (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      slug TEXT NOT NULL UNIQUE,
      text_content TEXT,
      image_filename TEXT,
      display_order INTEGER
    );
    """)
    
    # NOVO - Tabela 7: Galeria de Imagens
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS gallery_images (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      filename TEXT NOT NULL,
      display_order INTEGER
    );
    """)

    # --- Insere os valores padrão (se não existirem) ---
    cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", ('sobre_texto', DEFAULT_SOBRE_TEXTO))
    cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", ('sobre_imagem_filename', DEFAULT_SOBRE_IMAGEM_FILENAME))
    cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", ('background_image_filename', DEFAULT_BACKGROUND_IMAGE_FILENAME))
    
    defaults_contatos = {
        'contato_endereco': 'Rua Exemplo, 123 - Bairro Modelo, Rio de Janeiro - RJ',
        'contato_email': 'contato@olhardaperifa.com.br',
        'contato_telefones': '(21) 99999-8888, (21) 98888-7777'
    }
    for key, value in defaults_contatos.items():
        cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (key, value))

    db.commit()
    try_alter_tables(db)


def try_alter_tables(db):
    try:
        db.execute("ALTER TABLE projetos ADD COLUMN lider_membro_id INTEGER REFERENCES membros(id)")
        db.commit()
    except sqlite3.OperationalError:
        pass # Coluna já existe

    try:
        db.execute("ALTER TABLE projetos ADD COLUMN data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP")
        db.commit()
    except sqlite3.OperationalError:
        pass # Coluna já existe


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


# ----------- Funções Auxiliares (Helpers) -----------

def get_carousel_images():
    images = []
    try:
        for f in os.listdir(app.config['UPLOAD_FOLDER']):
            if os.path.isfile(os.path.join(app.config['UPLOAD_FOLDER'], f)) and allowed_file(f):
                images.append(f)
    except FileNotFoundError:
        app.logger.error("Pasta de Upload não encontrada (get_carousel_images).")
    return images

def get_projetos():
    db = get_db()
    cursor = db.execute("""
        SELECT p.*, m.nome AS nome_lider
        FROM projetos p
        LEFT JOIN membros m ON p.lider_membro_id = m.id
        ORDER BY p.data_criacao DESC
    """)
    return cursor.fetchall()

def get_sobre_data():
    db = get_db()
    cursor = db.execute("SELECT key, value FROM config WHERE key = 'sobre_texto' OR key = 'sobre_imagem_filename'")
    results = cursor.fetchall()
    data = {'texto': DEFAULT_SOBRE_TEXTO, 'imagem_filename': DEFAULT_SOBRE_IMAGEM_FILENAME}
    for row in results:
        if row['key'] == 'sobre_texto': data['texto'] = row['value']
        elif row['key'] == 'sobre_imagem_filename': data['imagem_filename'] = row['value']
    return data

def get_membros():
    db = get_db()
    cursor = db.execute("SELECT * FROM membros ORDER BY nome")
    return cursor.fetchall()

def get_contatos():
    db = get_db()
    cursor = db.execute("SELECT key, value FROM config WHERE key LIKE 'contato_%'")
    results = cursor.fetchall()
    defaults = {'contato_endereco': '', 'contato_email': '', 'contato_telefones': ''}
    db_contatos = {row['key']: row['value'] for row in results}
    contatos = {}
    for key in defaults:
        contatos[key.replace('contato_', '')] = db_contatos.get(key, defaults[key])
    return contatos

def get_background_image():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT value FROM config WHERE key = 'background_image_filename'")
    result = cursor.fetchone()
    return result['value'] if result and result['value'] else None

def get_custom_sections():
    """Busca todas as seções personalizadas, ordenadas."""
    db = get_db()
    cursor = db.execute("SELECT * FROM custom_sections ORDER BY display_order, id")
    return cursor.fetchall()

# NOVO: Helper para Galeria
def get_gallery_images():
    """Busca todas as imagens da galeria, ordenadas."""
    db = get_db()
    cursor = db.execute("SELECT * FROM gallery_images ORDER BY display_order, id")
    return cursor.fetchall()


# ----------- Rotas -----------

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        email = request.form.get('email', '').strip()
        tipo = request.form.get('tipo', '').strip()
        mensagem = request.form.get('mensagem', '').strip()

        if not nome or not email or not tipo:
            flash('Por favor preencha Nome, E-mail e Tipo de interesse.', 'danger')
            return redirect(url_for('index'))

        db = get_db()
        db.execute(
            "INSERT INTO interessados (nome, email, tipo, mensagem) VALUES (?, ?, ?, ?)",
            (nome, email, tipo, mensagem)
        )
        db.commit()
        flash('Obrigado! Seu interesse foi registrado.', 'success')
        return redirect(url_for('index'))

    carousel_images = get_carousel_images()
    projetos = get_projetos()
    sobre_data = get_sobre_data()
    contatos = get_contatos()
    background_image_filename = get_background_image()
    custom_sections = get_custom_sections() 
    gallery_images = get_gallery_images() # NOVO
    
    return render_template('index.html', 
                           carousel_images=carousel_images, 
                           projetos=projetos, 
                           sobre_data=sobre_data,
                           contatos=contatos,
                           background_image_filename=background_image_filename,
                           custom_sections=custom_sections,
                           gallery_images=gallery_images) # NOVO


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

    background_image_filename = get_background_image()
    custom_sections = get_custom_sections() 
    
    return render_template('login.html', 
                           background_image_filename=background_image_filename,
                           custom_sections=custom_sections) 


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
    
    carousel_images = get_carousel_images()
    projetos = get_projetos()
    sobre_data = get_sobre_data()
    membros = get_membros()
    contatos = get_contatos()
    background_image_filename = get_background_image()
    custom_sections = get_custom_sections() 
    gallery_images = get_gallery_images() # NOVO
    
    return render_template('admin.html', 
                           entries=entries, 
                           carousel_images=carousel_images, 
                           projetos=projetos, 
                           sobre_data=sobre_data,
                           membros=membros,
                           contatos=contatos,
                           background_image_filename=background_image_filename,
                           custom_sections=custom_sections,
                           gallery_images=gallery_images) # NOVO


@app.route('/delete/<int:entry_id>', methods=['POST'])
@login_required
def delete_entry(entry_id):
    db = get_db()
    db.execute("DELETE FROM interessados WHERE id = ?", (entry_id,))
    db.commit()
    flash('Registro excluído.', 'success')
    return redirect(url_for('admin'))


@app.route('/export.csv')
@login_required
def export_csv():
    # (código inalterado)
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
    return Response(output, mimetype="text/csv", headers={"Content-Disposition":"attachment;filename=interessados.csv"})


# ----------- Rotas de Gerenciamento (Admin) -----------

# (Rotas de Carrossel, Sobre, Contatos, Fundo, Membros... inalteradas)
# --- Upload de Imagem (Carrossel) ---
@app.route('/admin/upload', methods=['POST'])
@login_required
def admin_upload():
    if 'file' not in request.files:
        flash('Nenhum arquivo selecionado.', 'danger')
        return redirect(url_for('admin'))
    file = request.files['file']
    if file.filename == '':
        flash('Nenhum arquivo selecionado.', 'danger')
        return redirect(url_for('admin'))
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        flash('Imagem enviada para o carrossel!', 'success')
    else:
        flash('Tipo de arquivo não permitido.', 'danger')
    return redirect(url_for('admin'))

# --- Excluir Imagem (Carrossel) ---
@app.route('/admin/delete_image/<string:filename>', methods=['POST'])
@login_required
def admin_delete_image(filename):
    try:
        filename = secure_filename(filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            flash(f'Imagem {filename} excluída.', 'success')
        else:
            flash('Arquivo não encontrado.', 'warning')
    except Exception as e:
        flash(f'Erro ao excluir imagem: {e}', 'danger')
        app.logger.error(f"Erro ao excluir imagem {filename}: {e}")
    return redirect(url_for('admin'))

# --- Atualizar Texto "Sobre" ---
@app.route('/admin/update_sobre', methods=['POST'])
@login_required
def admin_update_sobre():
    texto = request.form.get('sobre_texto', DEFAULT_SOBRE_TEXTO)
    db = get_db()
    db.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ('sobre_texto', texto))
    db.commit()
    flash("Texto 'Sobre' atualizado.", 'success')
    return redirect(url_for('admin'))

# --- Upload de Imagem "Sobre" ---
@app.route('/admin/upload_sobre_imagem', methods=['POST'])
@login_required
def admin_upload_sobre_imagem():
    if 'file' not in request.files:
        flash('Nenhum arquivo selecionado.', 'danger')
        return redirect(url_for('admin'))
    file = request.files['file']
    if file.filename == '':
        flash('Nenhum arquivo selecionado.', 'danger')
        return redirect(url_for('admin'))
    if file and allowed_file(file.filename):
        db = get_db()
        old_filename = get_sobre_data().get('imagem_filename')
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        db.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ('sobre_imagem_filename', filename))
        db.commit()
        if old_filename and old_filename != filename:
            try:
                old_filepath = os.path.join(app.config['UPLOAD_FOLDER'], old_filename)
                if os.path.exists(old_filepath):
                    os.remove(old_filepath)
            except Exception as e:
                app.logger.error(f"Erro ao excluir imagem 'Sobre' antiga: {e}")
        flash('Imagem "Sobre" atualizada!', 'success')
    else:
        flash('Tipo de arquivo não permitido.', 'danger')
    return redirect(url_for('admin'))

# --- Atualizar "Contatos" ---
@app.route('/admin/update_contatos', methods=['POST'])
@login_required
def admin_update_contatos():
    db = get_db()
    try:
        contatos = {
            'contato_endereco': request.form.get('contato_endereco', ''),
            'contato_email': request.form.get('contato_email', ''),
            'contato_telefones': request.form.get('contato_telefones', '')
        }
        for key, value in contatos.items():
            db.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
        db.commit()
        flash("Informações de Contato atualizadas.", 'success')
    except Exception as e:
        db.rollback()
        flash(f"Erro ao salvar contatos: {e}", 'danger')
        app.logger.error(f"Erro em admin_update_contatos: {e}")
    return redirect(url_for('admin'))

# --- Rota "Background" (Fundo do Site) ---
@app.route('/admin/upload_background', methods=['POST'])
@login_required
def admin_upload_background():
    if 'file' not in request.files:
        flash('Nenhum arquivo selecionado.', 'danger')
        return redirect(url_for('admin'))
    file = request.files['file']
    if file.filename == '':
        flash('Nenhum arquivo selecionado.', 'danger')
        return redirect(url_for('admin'))
    if file and allowed_file(file.filename):
        db = get_db()
        old_filename = get_background_image()
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        db.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ('background_image_filename', filename))
        db.commit()
        if old_filename and old_filename != filename:
            try:
                old_filepath = os.path.join(app.config['UPLOAD_FOLDER'], old_filename)
                if os.path.exists(old_filepath):
                    os.remove(old_filepath)
            except Exception as e:
                app.logger.error(f"Erro ao excluir imagem de fundo antiga: {e}")
        flash('Imagem de fundo do site atualizada!', 'success')
    else:
        flash('Tipo de arquivo não permitido.', 'danger')
    return redirect(url_for('admin'))

@app.route('/admin/delete_background', methods=['POST'])
@login_required
def admin_delete_background():
    db = get_db()
    old_filename = get_background_image()
    if old_filename:
        try:
            old_filepath = os.path.join(app.config['UPLOAD_FOLDER'], old_filename)
            if os.path.exists(old_filepath):
                os.remove(old_filepath)
        except Exception as e:
            app.logger.error(f"Erro ao excluir imagem de fundo: {e}")
    db.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ('background_image_filename', None))
    db.commit()
    flash('Imagem de fundo removida. O site voltou para a cor amarela.', 'success')
    return redirect(url_for('admin'))

# --- Rotas de Membros ---
@app.route('/admin/membro/add', methods=['POST'])
@login_required
def admin_add_membro():
    nome = request.form.get('nome', '').strip()
    email = request.form.get('email', '').strip()
    if not nome or not email:
        flash('Nome e E-mail são obrigatórios.', 'danger')
        return redirect(url_for('admin'))
    db = get_db()
    try:
        db.execute("INSERT INTO membros (nome, email) VALUES (?, ?)", (nome, email))
        db.commit()
        flash(f"Membro {nome} adicionado.", 'success')
    except sqlite3.IntegrityError:
        flash(f"Erro: O e-mail {email} já está cadastrado.", 'danger')
    except Exception as e:
        flash(f"Erro ao adicionar membro: {e}", 'danger')
    return redirect(url_for('admin'))

@app.route('/admin/membro/delete/<int:membro_id>', methods=['POST'])
@login_required
def admin_delete_membro(membro_id):
    db = get_db()
    try:
        db.execute("DELETE FROM membros WHERE id = ?", (membro_id,))
        db.commit()
        flash('Membro excluído.', 'success')
    except Exception as e:
        flash(f"Erro ao excluir membro: {e}", 'danger')
    return redirect(url_for('admin'))


# --- Rotas de Projetos ---
@app.route('/admin/projeto/add', methods=['POST'])
@login_required
def admin_add_projeto():
    titulo = request.form.get('titulo', '').strip()
    descricao = request.form.get('descricao', '').strip()
    if 'file' not in request.files or request.files['file'].filename == '':
        flash('Uma imagem é obrigatória para o projeto.', 'danger')
        return redirect(url_for('admin'))
    if not titulo or not descricao:
        flash('Título e Descrição são obrigatórios.', 'danger')
        return redirect(url_for('admin'))
    file = request.files['file']
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER_PROJETOS'], filename)
        file.save(filepath)
        db = get_db()
        db.execute(
            "INSERT INTO projetos (titulo, descricao, imagem_filename) VALUES (?, ?, ?)",
            (titulo, descricao, filename)
        )
        db.commit()
        flash(f'Projeto "{titulo}" criado!', 'success')
    else:
        flash('Tipo de arquivo não permitido.', 'danger')
    return redirect(url_for('admin'))

@app.route('/admin/projeto/delete/<int:projeto_id>', methods=['POST'])
@login_required
def admin_delete_projeto(projeto_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT imagem_filename FROM projetos WHERE id = ?", (projeto_id,))
    result = cursor.fetchone()
    if result:
        db.execute("DELETE FROM projetos WHERE id = ?", (projeto_id,))
        db.commit()
        try:
            filename = result['imagem_filename']
            filepath = os.path.join(app.config['UPLOAD_FOLDER_PROJETOS'], filename)
            if os.path.exists(filepath):
                os.remove(filepath)
            flash('Projeto excluído.', 'success')
        except Exception as e:
            flash(f'Projeto excluído do banco, mas falha ao apagar arquivo: {e}', 'warning')
            app.logger.error(f"Erro ao excluir arquivo de projeto: {e}")
    else:
        flash('Projeto não encontrado.', 'danger')
    return redirect(url_for('admin'))


# --- Rotas de Gerenciamento de Equipe ---
@app.route('/admin/projeto/<int:projeto_id>/equipe', methods=['GET'])
@login_required
def admin_gerenciar_equipe(projeto_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT p.*, m.nome AS nome_lider
        FROM projetos p
        LEFT JOIN membros m ON p.lider_membro_id = m.id
        WHERE p.id = ?
    """, (projeto_id,))
    projeto = cursor.fetchone()
    if not projeto:
        flash('Projeto não encontrado.', 'danger')
        return redirect(url_for('admin'))
    all_membros = get_membros()
    cursor.execute("""
        SELECT m.id, m.nome, m.email
        FROM membros m
        JOIN projetos_membros pm ON m.id = pm.membro_id
        WHERE pm.projeto_id = ?
    """, (projeto_id,))
    equipe_atual = cursor.fetchall()
    ids_equipe_atual = [m['id'] for m in equipe_atual]
    membros_disponiveis = [m for m in all_membros if m['id'] not in ids_equipe_atual]
    background_image_filename = get_background_image()
    custom_sections = get_custom_sections() 
    
    return render_template('projeto_equipe.html', 
                           projeto=projeto, 
                           all_membros=all_membros,
                           equipe_atual=equipe_atual,
                           membros_disponiveis=membros_disponiveis,
                           background_image_filename=background_image_filename,
                           custom_sections=custom_sections) 

@app.route('/admin/projeto/<int:projeto_id>/set_lider', methods=['POST'])
@login_required
def admin_set_lider(projeto_id):
    lider_id = request.form.get('lider_id', 0, type=int)
    db = get_db()
    if lider_id == 0:
        db.execute("UPDATE projetos SET lider_membro_id = NULL WHERE id = ?", (projeto_id,))
        flash('Líder removido do projeto.', 'info')
    else:
        db.execute("UPDATE projetos SET lider_membro_id = ? WHERE id = ?", (lider_id, projeto_id))
        flash('Novo líder definido para o projeto.', 'success')
    db.commit()
    return redirect(url_for('admin_gerenciar_equipe', projeto_id=projeto_id))

@app.route('/admin/projeto/<int:projeto_id>/add_membro', methods=['POST'])
@login_required
def admin_add_membro_projeto(projeto_id):
    membro_id = request.form.get('membro_id', 0, type=int)
    if membro_id == 0:
        flash('Nenhum membro selecionado.', 'warning')
        return redirect(url_for('admin_gerenciar_equipe', projeto_id=projeto_id))
    db = get_db()
    try:
        db.execute("INSERT INTO projetos_membros (projeto_id, membro_id) VALUES (?, ?)", (projeto_id, membro_id))
        db.commit()
        flash('Membro adicionado à equipe.', 'success')
    except sqlite3.IntegrityError:
        flash('Este membro já está na equipe.', 'warning')
    except Exception as e:
        flash(f'Erro ao adicionar membro: {e}', 'danger')
    return redirect(url_for('admin_gerenciar_equipe', projeto_id=projeto_id))

@app.route('/admin/projeto/<int:projeto_id>/remove_membro/<int:membro_id>', methods=['POST'])
@login_required
def admin_remove_membro_projeto(projeto_id, membro_id):
    db = get_db()
    try:
        db.execute("DELETE FROM projetos_membros WHERE projeto_id = ? AND membro_id = ?", (projeto_id, membro_id))
        cursor = db.cursor()
        cursor.execute("SELECT lider_membro_id FROM projetos WHERE id = ?", (projeto_id,))
        projeto = cursor.fetchone()
        if projeto and projeto['lider_membro_id'] == membro_id:
            db.execute("UPDATE projetos SET lider_membro_id = NULL WHERE id = ?", (projeto_id,))
            flash('Membro removido da equipe (ele também era o líder).', 'success')
        else:
            flash('Membro removido da equipe.', 'success')
        db.commit()
    except Exception as e:
        flash(f'Erro ao remover membro: {e}', 'danger')
    return redirect(url_for('admin_gerenciar_equipe', projeto_id=projeto_id))


# --- Rotas de Seções Personalizadas ---

@app.route('/admin/section/add', methods=['POST'])
@login_required
def admin_add_section():
    title = request.form.get('title', '').strip()
    text_content = request.form.get('text_content', '').strip()
    
    if not title or not text_content:
        flash('Título e Texto são obrigatórios.', 'danger')
        return redirect(url_for('admin'))
        
    if 'file' not in request.files or request.files['file'].filename == '':
        flash('Uma imagem é obrigatória para a seção.', 'danger')
        return redirect(url_for('admin'))
        
    file = request.files['file']
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # Salva na pasta específica de CUSTOM
        filepath = os.path.join(app.config['UPLOAD_FOLDER_CUSTOM'], filename)
        file.save(filepath)
        
        # Cria o slug
        slug = slugify(title)
        
        db = get_db()
        try:
            # Pega a próxima ordem de exibição
            cursor = db.cursor()
            cursor.execute("SELECT MAX(display_order) as max_order FROM custom_sections")
            max_order = cursor.fetchone()['max_order'] or 0
            new_order = max_order + 1
            
            db.execute(
                "INSERT INTO custom_sections (title, slug, text_content, image_filename, display_order) VALUES (?, ?, ?, ?, ?)",
                (title, slug, text_content, filename, new_order)
            )
            db.commit()
            flash(f'Nova seção "{title}" criada!', 'success')
        except sqlite3.IntegrityError:
            flash(f'Erro: Uma seção com o título "{title}" (ou slug "{slug}") já existe. Tente um título diferente.', 'danger')
        except Exception as e:
            flash(f'Erro ao criar seção: {e}', 'danger')
    else:
        flash('Tipo de arquivo não permitido.', 'danger')

    return redirect(url_for('admin'))


@app.route('/admin/section/delete/<int:section_id>', methods=['POST'])
@login_required
def admin_delete_section(section_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT image_filename FROM custom_sections WHERE id = ?", (section_id,))
    result = cursor.fetchone()
    
    if result:
        db.execute("DELETE FROM custom_sections WHERE id = ?", (section_id,))
        db.commit()
        
        try:
            filename = result['image_filename']
            filepath = os.path.join(app.config['UPLOAD_FOLDER_CUSTOM'], filename)
            if os.path.exists(filepath):
                os.remove(filepath)
            flash('Seção personalizada excluída.', 'success')
        except Exception as e:
            flash(f'Seção excluída do banco, mas falha ao apagar arquivo: {e}', 'warning')
            app.logger.error(f"Erro ao excluir arquivo de seção: {e}")
    else:
        flash('Seção não encontrada.', 'danger')

    return redirect(url_for('admin'))

# --- NOVO: Rotas da Galeria "Nossa Galera" ---

@app.route('/admin/gallery/add', methods=['POST'])
@login_required
def admin_add_gallery_image():
    if 'file' not in request.files:
        flash('Nenhum arquivo selecionado.', 'danger')
        return redirect(url_for('admin'))
    
    file = request.files['file']
    
    if file.filename == '':
        flash('Nenhum arquivo selecionado.', 'danger')
        return redirect(url_for('admin'))
        
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER_GALLERY'], filename)
        file.save(filepath)
        
        db = get_db()
        try:
            # Pega a próxima ordem de exibição
            cursor = db.cursor()
            cursor.execute("SELECT MAX(display_order) as max_order FROM gallery_images")
            max_order = cursor.fetchone()['max_order'] or 0
            new_order = max_order + 1
            
            db.execute(
                "INSERT INTO gallery_images (filename, display_order) VALUES (?, ?)",
                (filename, new_order)
            )
            db.commit()
            flash('Nova foto adicionada à galeria "Nossa Galera"!', 'success')
        except Exception as e:
            flash(f'Erro ao salvar foto na galeria: {e}', 'danger')
    else:
        flash('Tipo de arquivo não permitido.', 'danger')

    return redirect(url_for('admin'))


@app.route('/admin/gallery/delete/<int:image_id>', methods=['POST'])
@login_required
def admin_delete_gallery_image(image_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT filename FROM gallery_images WHERE id = ?", (image_id,))
    result = cursor.fetchone()
    
    if result:
        db.execute("DELETE FROM gallery_images WHERE id = ?", (image_id,))
        db.commit()
        
        try:
            filename = result['filename']
            filepath = os.path.join(app.config['UPLOAD_FOLDER_GALLERY'], filename)
            if os.path.exists(filepath):
                os.remove(filepath)
            flash('Foto da galeria excluída.', 'success')
        except Exception as e:
            flash(f'Foto excluída do banco, mas falha ao apagar arquivo: {e}', 'warning')
            app.logger.error(f"Erro ao excluir arquivo de galeria: {e}")
    else:
        flash('Foto da galeria não encontrada.', 'danger')

    return redirect(url_for('admin'))


# ----------- Main -----------

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO) # Adiciona log
    with app.app_context():
        init_db()
    app.run(debug=True)
