import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, session, g
from werkzeug.security import generate_password_hash, check_password_hash
import os
from werkzeug.utils import secure_filename # Importação necessária
import logging # Para debug

# Configurações básicas
APP_SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'troque_esta_chave_para_producao')
ADMIN_USERNAME = os.environ.get('ADMIN_USER', 'admin')
DEFAULT_ADMIN_PASSWORD = os.environ.get('ADMIN_PASS', 'senha123')

# --- Configurações de Upload ---
# Pasta para o Carrossel
UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static/uploads')
# NOVA Pasta para os Projetos
UPLOAD_FOLDER_PROJETOS = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static/uploads/projetos')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app = Flask(__name__)
app.config['SECRET_KEY'] = APP_SECRET_KEY
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER # Pasta do Carrossel
app.config['UPLOAD_FOLDER_PROJETOS'] = UPLOAD_FOLDER_PROJETOS # Pasta dos Projetos
DATABASE = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'database.db')

ADMIN_PASSWORD_HASH = generate_password_hash(DEFAULT_ADMIN_PASSWORD)

# Texto padrão da seção "Sobre"
DEFAULT_SOBRE_TEXTO = """Em 2024 nos tornamos ONG, com 6 membros colaboradores em 5 atividades: Fotografia, produção cultural, Passeio Histórico, Direitos humanos e Artes visuais. Atendemos desde de 2023 cerca de 70 alunos nas atividades. Atuamos em uma região periférica onde não há fomento a cultura.
Hoje somos reconhecidos como Ponto de Cultura pelo Estado do Rio de Janeiro e Ponto de Memória pelo IBRAM.
Em Janeiro desse ano tivemos a primeira Mostra Multicultural a Mostra Ubuntu. Onde fizemos girar a economia criativa da região com contratação de 60 pessoas sendo 30 artistas e 30 trabalhadores de Cultura, tudo através da Lei de fomento a Cultura Paulo Gustavo.
Nosso atual objetivo é conseguir fomento para continuar as ações e ampliar o projeto."""

# --- Valores Padrão para Contatos (NOVO) ---
DEFAULT_CONTATO_ENDERECO = "Av. Principal, 123, Bairro - Cidade/RJ"
DEFAULT_CONTATO_EMAIL = "contato@olhardaperifa.com.br"
DEFAULT_CONTATO_TELEFONES = "(21) 99999-8888, (21) 2222-3333"
# NOVO: Nome padrão para a imagem "Sobre"
DEFAULT_SOBRE_IMAGEM_FILENAME = None # Começa sem imagem


def allowed_file(filename):
    """Verifica se a extensão do arquivo é permitida"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ----------- Banco de Dados -----------

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


def init_db_alter_tables():
    """Tenta adicionar colunas a tabelas existentes. Seguro para rodar."""
    db = get_db()
    cursor = db.cursor()
    
    try:
        # Tenta adicionar a coluna de líder na tabela de projetos
        cursor.execute("ALTER TABLE projetos ADD COLUMN lider_membro_id INTEGER REFERENCES membros(id)")
        app.logger.info("Coluna 'lider_membro_id' adicionada a 'projetos'.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            pass # Coluna já existe, tudo bem.
        else:
            raise e # Outro erro
            
    db.commit()


def init_db():
    # Cria as pastas de uploads se não existirem
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(UPLOAD_FOLDER_PROJETOS, exist_ok=True)
    
    db = get_db()
    cursor = db.cursor()
    
    # Tabela de Interessados
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
    
    # Tabela de Projetos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS projetos (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      titulo TEXT NOT NULL,
      descricao TEXT NOT NULL,
      imagem_filename TEXT NOT NULL,
      lider_membro_id INTEGER REFERENCES membros(id)
    );
    """)
    
    # Tabela de Configuração (para o texto "Sobre" e "Contatos")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS config (
      key TEXT PRIMARY KEY,
      value TEXT
    );
    """)
    
    # Tabela de Membros
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS membros (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      nome TEXT NOT NULL,
      email TEXT NOT NULL UNIQUE
    );
    """)
    
    # Tabela de Associação (Muitos-para-Muitos)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS projetos_membros (
      projeto_id INTEGER NOT NULL,
      membro_id INTEGER NOT NULL,
      FOREIGN KEY(projeto_id) REFERENCES projetos(id) ON DELETE CASCADE,
      FOREIGN KEY(membro_id) REFERENCES membros(id) ON DELETE CASCADE,
      PRIMARY KEY (projeto_id, membro_id)
    );
    """)
    
    # Insere o texto "Sobre" padrão se ele não existir
    cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", ('sobre_texto', DEFAULT_SOBRE_TEXTO))
    # NOVO: Insere a imagem "Sobre" padrão (nula)
    cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", ('sobre_imagem_filename', DEFAULT_SOBRE_IMAGEM_FILENAME))
    
    # --- Insere os Contatos Padrão (NOVO) ---
    cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", ('contato_endereco', DEFAULT_CONTATO_ENDERECO))
    cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", ('contato_email', DEFAULT_CONTATO_EMAIL))
    cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", ('contato_telefones', DEFAULT_CONTATO_TELEFONES))
    
    db.commit()


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


# ----------- Funções Auxiliares (Helpers) -----------

def get_carousel_images():
    """Helper para ler as imagens do carrossel da pasta de uploads."""
    images = []
    if os.path.exists(app.config['UPLOAD_FOLDER']):
        images = [f for f in os.listdir(app.config['UPLOAD_FOLDER']) if allowed_file(f)]
    return images

def get_projetos():
    """Helper para ler os projetos e seus líderes do banco de dados."""
    db = get_db()
    cursor = db.cursor()
    # Usamos LEFT JOIN para pegar o nome do líder, mesmo que não haja um (lider_membro_id seja NULL)
    cursor.execute("""
        SELECT 
            p.*, 
            m.nome as nome_lider
        FROM projetos p
        LEFT JOIN membros m ON p.lider_membro_id = m.id
        ORDER BY p.id DESC
    """)
    return cursor.fetchall()

def get_sobre_data():
    """Helper para ler os dados "Sobre" (texto e imagem) do banco."""
    db = get_db()
    cursor = db.cursor()
    
    # Busca o texto
    cursor.execute("SELECT value FROM config WHERE key = 'sobre_texto'")
    result_texto = cursor.fetchone()
    
    # Busca a imagem
    cursor.execute("SELECT value FROM config WHERE key = 'sobre_imagem_filename'")
    result_imagem = cursor.fetchone()

    return {
        'texto': result_texto['value'] if result_texto else DEFAULT_SOBRE_TEXTO,
        'imagem_filename': result_imagem['value'] if result_imagem else DEFAULT_SOBRE_IMAGEM_FILENAME
    }

def get_membros():
    """Helper para ler todos os membros da ONG."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM membros ORDER BY nome")
    return cursor.fetchall()

def get_contatos():
    """Helper para ler as informações de contato (NOVO)."""
    db = get_db()
    cursor = db.cursor()
    contatos = {}
    
    keys = ['contato_endereco', 'contato_email', 'contato_telefones']
    defaults = {
        'contato_endereco': DEFAULT_CONTATO_ENDERECO,
        'contato_email': DEFAULT_CONTATO_EMAIL,
        'contato_telefones': DEFAULT_CONTATO_TELEFONES
    }
    
    for key in keys:
        cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
        result = cursor.fetchone()
        contatos[key.replace('contato_', '')] = result['value'] if result else defaults[key]
        
    return contatos


# ----------- Rotas -----------

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Lógica do Formulário de Contato
        nome = request.form.get('nome', '').strip()
        email = request.form.get('email', '').strip()
        tipo = request.form.get('tipo', '').strip()
        mensagem = request.form.get('mensagem', '').strip()

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

    # Prepara dados para a página inicial
    carousel_images = get_carousel_images()
    projetos = get_projetos()
    sobre_data = get_sobre_data() # ATUALIZADO
    contatos = get_contatos() # (NOVO)
    
    return render_template('index.html', 
                           carousel_images=carousel_images, 
                           projetos=projetos, 
                           sobre_data=sobre_data, # ATUALIZADO
                           contatos=contatos) # (NOVO)


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
    
    carousel_images = get_carousel_images()
    projetos = get_projetos()
    sobre_data = get_sobre_data() # ATUALIZADO
    membros = get_membros() # Busca os membros
    contatos = get_contatos() # (NOVO)
    
    return render_template('admin.html', 
                           entries=entries, 
                           carousel_images=carousel_images, 
                           projetos=projetos, 
                           sobre_data=sobre_data, # ATUALIZADO
                           membros=membros,
                           contatos=contatos) # (NOVO)


@app.route('/delete/<int:entry_id>', methods=['POST'])
@login_required
def delete_entry(entry_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM interessados WHERE id = ?", (entry_id,))
    db.commit()
    flash('Registro excluído.', 'success')
    return redirect(url_for('admin'))


# ----------- Rotas Carrossel -----------

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
        flash('Imagem do carrossel enviada!', 'success')
    else:
        flash('Tipo de arquivo não permitido.', 'danger')
        
    return redirect(url_for('admin'))


@app.route('/admin/delete_image/<path:filename>', methods=['POST'])
@login_required
def admin_delete_image(filename):
    try:
        filename = secure_filename(filename) 
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        if os.path.exists(filepath):
            os.remove(filepath)
            flash('Imagem do carrossel excluída.', 'success')
        else:
            flash('Arquivo não encontrado.', 'warning')
    except Exception as e:
        flash(f'Erro ao excluir imagem: {e}', 'danger')
        
    return redirect(url_for('admin'))

# ----------- Rotas de Projetos -----------

@app.route('/admin/add_projeto', methods=['POST'])
@login_required
def admin_add_projeto():
    titulo = request.form.get('titulo', '').strip()
    descricao = request.form.get('descricao', '').strip()
    
    if 'file' not in request.files or request.files['file'].filename == '':
        flash('A imagem do projeto é obrigatória.', 'danger')
        return redirect(url_for('admin'))
        
    if not titulo or not descricao:
        flash('Título e Descrição são obrigatórios.', 'danger')
        return redirect(url_for('admin'))

    file = request.files['file']

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER_PROJETOS'], filename))
        
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            # A coluna 'lider_membro_id' começa como NULL (vazia)
            "INSERT INTO projetos (titulo, descricao, imagem_filename) VALUES (?, ?, ?)",
            (titulo, descricao, filename)
        )
        db.commit()
        flash('Novo projeto adicionado com sucesso!', 'success')
    else:
        flash('Erro: Tipo de arquivo não permitido ou arquivo inválido.', 'danger')
        
    return redirect(url_for('admin'))


@app.route('/admin/delete_projeto/<int:projeto_id>', methods=['POST'])
@login_required
def admin_delete_projeto(projeto_id):
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("SELECT imagem_filename FROM projetos WHERE id = ?", (projeto_id,))
    projeto = cursor.fetchone()
    
    if projeto:
        try:
            # Exclui a imagem do projeto
            filename = projeto['imagem_filename']
            filepath = os.path.join(app.config['UPLOAD_FOLDER_PROJETOS'], filename)
            if os.path.exists(filepath):
                os.remove(filepath)
                
            # Exclui o projeto (ON DELETE CASCADE cuidará das associações)
            cursor.execute("DELETE FROM projetos WHERE id = ?", (projeto_id,))
            db.commit()
            flash('Projeto excluído com sucesso.', 'success')
            
        except Exception as e:
            flash(f'Erro ao excluir o projeto: {e}', 'danger')
    else:
        flash('Projeto não encontrado.', 'warning')
        
    return redirect(url_for('admin'))

# ----------- Rota "Sobre" -----------

@app.route('/admin/update_sobre', methods=['POST'])
@login_required
def admin_update_sobre():
    novo_texto = request.form.get('sobre_texto', '')
    
    db = get_db()
    db.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ('sobre_texto', novo_texto))
    db.commit()
    
    flash('Texto "Sobre a ONG" atualizado com sucesso!', 'success')
    return redirect(url_for('admin'))

# NOVO: Rota para upload da IMAGEM "Sobre"
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
        # 1. Pega o nome da imagem antiga (se existir) para excluí-la
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT value FROM config WHERE key = 'sobre_imagem_filename'")
        old_image_result = cursor.fetchone()
        
        # 2. Salva a nova imagem
        filename = secure_filename(file.filename)
        # Vamos garantir um nome único para evitar cache, mas pode ser só o filename
        # Para simplificar, vamos usar o nome seguro do arquivo
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # 3. Atualiza o banco de dados com o novo nome
        db.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ('sobre_imagem_filename', filename))
        db.commit()
        
        # 4. Exclui a imagem antiga (se existir e for diferente da nova)
        if old_image_result and old_image_result['value']:
            old_filename = old_image_result['value']
            if old_filename != filename:
                try:
                    old_filepath = os.path.join(app.config['UPLOAD_FOLDER'], old_filename)
                    if os.path.exists(old_filepath):
                        os.remove(old_filepath)
                except Exception as e:
                    app.logger.error(f"Erro ao excluir imagem antiga 'Sobre': {e}")
                    
        flash('Imagem da seção "Sobre" atualizada!', 'success')
    else:
        flash('Tipo de arquivo não permitido.', 'danger')
        
    return redirect(url_for('admin'))


# ----------- Rota "Contatos" (NOVO) -----------

@app.route('/admin/update_contatos', methods=['POST'])
@login_required
def admin_update_contatos():
    endereco = request.form.get('contato_endereco', '').strip()
    email = request.form.get('contato_email', '').strip()
    telefones = request.form.get('contato_telefones', '').strip()
    
    db = get_db()
    db.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ('contato_endereco', endereco))
    db.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ('contato_email', email))
    db.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ('contato_telefones', telefones))
    db.commit()
    
    flash('Informações de contato atualizadas com sucesso!', 'success')
    return redirect(url_for('admin'))


# ----------- Rotas de Membros -----------

@app.route('/admin/add_membro', methods=['POST'])
@login_required
def admin_add_membro():
    nome = request.form.get('nome', '').strip()
    email = request.form.get('email', '').strip()
    
    if not nome or not email:
        flash('Nome e E-mail são obrigatórios para o membro.', 'danger')
        return redirect(url_for('admin'))
        
    db = get_db()
    try:
        db.execute("INSERT INTO membros (nome, email) VALUES (?, ?)", (nome, email))
        db.commit()
        flash('Novo membro adicionado!', 'success')
    except sqlite3.IntegrityError:
        flash('Erro: Já existe um membro com esse e-mail.', 'danger')
        
    return redirect(url_for('admin'))


@app.route('/admin/delete_membro/<int:membro_id>', methods=['POST'])
@login_required
def admin_delete_membro(membro_id):
    db = get_db()
    # ON DELETE CASCADE cuidará de remover o membro das equipes e de 
    # definir como NULL o 'lider_membro_id' (se a FK for configurada, senão temos que fazer manual)
    # Por segurança, vamos setar o líder como NULL manualmente
    db.execute("UPDATE projetos SET lider_membro_id = NULL WHERE lider_membro_id = ?", (membro_id,))
    db.execute("DELETE FROM membros WHERE id = ?", (membro_id,))
    db.commit()
    flash('Membro excluído com sucesso.', 'success')
    return redirect(url_for('admin'))


# ----------- Rotas de Gerenciamento de Equipe -----------

@app.route('/admin/projeto/<int:projeto_id>/equipe', methods=['GET'])
@login_required
def admin_gerenciar_equipe(projeto_id):
    db = get_db()
    cursor = db.cursor()
    
    # 1. Pega dados do projeto (e nome do líder)
    cursor.execute("""
        SELECT p.*, m.nome as nome_lider
        FROM projetos p
        LEFT JOIN membros m ON p.lider_membro_id = m.id
        WHERE p.id = ?
    """, (projeto_id,))
    projeto = cursor.fetchone()
    
    if not projeto:
        flash('Projeto não encontrado.', 'warning')
        return redirect(url_for('admin'))
        
    # 2. Pega todos os membros da ONG (para os dropdowns)
    all_membros = get_membros()
    
    # 3. Pega membros que JÁ ESTÃO na equipe
    cursor.execute("""
        SELECT m.* FROM membros m
        JOIN projetos_membros pm ON m.id = pm.membro_id
        WHERE pm.projeto_id = ?
    """, (projeto_id,))
    equipe_atual = cursor.fetchall()
    
    # 4. Pega membros que NÃO ESTÃO na equipe (para o dropdown de "adicionar")
    ids_equipe_atual = [m['id'] for m in equipe_atual]
    membros_disponiveis = [m for m in all_membros if m['id'] not in ids_equipe_atual]
    
    return render_template('projeto_equipe.html', 
                           projeto=projeto, 
                           all_membros=all_membros,
                           equipe_atual=equipe_atual,
                           membros_disponiveis=membros_disponiveis)


@app.route('/admin/projeto/<int:projeto_id>/set_lider', methods=['POST'])
@login_required
def admin_set_lider(projeto_id):
    lider_id = request.form.get('lider_id', 0, type=int)
    
    db = get_db()
    if lider_id == 0:
        # Define o líder como NULL (Nenhum)
        db.execute("UPDATE projetos SET lider_membro_id = NULL WHERE id = ?", (projeto_id,))
        flash('Líder removido do projeto.', 'info')
    else:
        # Define o novo líder
        db.execute("UPDATE projetos SET lider_membro_id = ? WHERE id = ?", (lider_id, projeto_id))
        # Bônus: Garante que o líder esteja na equipe
        db.execute("INSERT OR IGNORE INTO projetos_membros (projeto_id, membro_id) VALUES (?, ?)", (projeto_id, lider_id))
        flash('Novo líder definido para o projeto!', 'success')
        
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
        flash('Membro adicionado à equipe do projeto.', 'success')
    except sqlite3.IntegrityError:
        flash('Este membro já está na equipe.', 'warning')
        
    return redirect(url_for('admin_gerenciar_equipe', projeto_id=projeto_id))


@app.route('/admin/projeto/<int:projeto_id>/remove_membro/<int:membro_id>', methods=['POST'])
@login_required
def admin_remove_membro_projeto(projeto_id, membro_id):
    db = get_db()
    
    # Pega o líder atual para não permitir sua remoção (ele deve ser trocado primeiro)
    cursor = db.cursor()
    cursor.execute("SELECT lider_membro_id FROM projetos WHERE id = ?", (projeto_id,))
    projeto = cursor.fetchone()

    if projeto and projeto['lider_membro_id'] == membro_id:
        flash('Você não pode remover o líder da equipe. Troque o líder primeiro.', 'danger')
        return redirect(url_for('admin_gerenciar_equipe', projeto_id=projeto_id))
        
    db.execute("DELETE FROM projetos_membros WHERE projeto_id = ? AND membro_id = ?", (projeto_id, membro_id))
    db.commit()
    flash('Membro removido da equipe.', 'success')
    
    return redirect(url_for('admin_gerenciar_equipe', projeto_id=projeto_id))


# -----------------------------------------------------------

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
    with app.app_context():
        init_db()
        init_db_alter_tables() # Tenta atualizar as tabelas existentes
        
    # Modo debug facilita a apresentação
    app.run(debug=True)
