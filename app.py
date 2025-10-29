import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'tareas.db')

app = Flask(__name__)
app.secret_key = 'cambialo_por_una_clave_muy_segura'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    cur = db.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    );""")
    cur.execute("""CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        completed INTEGER NOT NULL DEFAULT 0,
        user_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );""")
    db.commit()

@app.before_request
def before_request():
    get_db()

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    db = get_db()
    user = db.execute('SELECT id, username, created_at FROM users WHERE id = ?', (uid,)).fetchone()
    return user

@app.route('/')
def index():
    user = current_user()
    db = get_db()
    if user:
        tasks = db.execute('SELECT * FROM tasks WHERE user_id = ? ORDER BY created_at DESC', (user['id'],)).fetchall()
    else:
        tasks = []
    return render_template('index.html', user=user, tasks=tasks)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        if not username or not password:
            flash('Por favor completa todos los campos.', 'danger')
            return redirect(url_for('register'))
        db = get_db()
        try:
            password_hash = generate_password_hash(password)
            db.execute('INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)',
                       (username, password_hash, datetime.utcnow().isoformat()))
            db.commit()
            flash('Registro exitoso. Ya puedes iniciar sesión.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('El nombre de usuario ya existe. Elige otro.', 'danger')
            return redirect(url_for('register'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            flash('Inicio de sesión correcto.', 'success')
            return redirect(url_for('dashboard'))
        flash('Usuario o contraseña incorrectos.', 'danger')
        return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Has cerrado sesión.', 'info')
    return redirect(url_for('index'))

def login_required(route_fn):
    from functools import wraps
    @wraps(route_fn)
    def wrapped(*args, **kwargs):
        if not current_user():
            flash('Necesitas iniciar sesión para acceder a esa página.', 'warning')
            return redirect(url_for('login'))
        return route_fn(*args, **kwargs)
    return wrapped

@app.route('/dashboard')
@login_required
def dashboard():
    user = current_user()
    db = get_db()
    tasks = db.execute('SELECT * FROM tasks WHERE user_id = ? ORDER BY created_at DESC', (user['id'],)).fetchall()
    return render_template('dashboard.html', user=user, tasks=tasks)

@app.route('/task/create', methods=['GET','POST'])
@login_required
def create_task():
    if request.method == 'POST':
        title = request.form['title'].strip()
        description = request.form.get('description','').strip()
        if not title:
            flash('El título es obligatorio.', 'danger')
            return redirect(url_for('create_task'))
        db = get_db()
        db.execute('INSERT INTO tasks (title, description, completed, user_id, created_at) VALUES (?, ?, ?, ?, ?)',
                   (title, description, 0, session['user_id'], datetime.utcnow().isoformat()))
        db.commit()
        flash('Tarea creada.', 'success')
        return redirect(url_for('dashboard'))
    return render_template('create_task.html')

@app.route('/task/edit/<int:task_id>', methods=['GET','POST'])
@login_required
def edit_task(task_id):
    db = get_db()
    task = db.execute('SELECT * FROM tasks WHERE id = ? AND user_id = ?', (task_id, session['user_id'])).fetchone()
    if not task:
        flash('Tarea no encontrada.', 'danger')
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        title = request.form['title'].strip()
        description = request.form.get('description','').strip()
        completed = 1 if request.form.get('completed') == 'on' else 0
        if not title:
            flash('El título es obligatorio.', 'danger')
            return redirect(url_for('edit_task', task_id=task_id))
        db.execute('UPDATE tasks SET title = ?, description = ?, completed = ? WHERE id = ?',
                   (title, description, completed, task_id))
        db.commit()
        flash('Tarea actualizada.', 'success')
        return redirect(url_for('dashboard'))
    return render_template('edit_task.html', task=task)

@app.route('/task/delete/<int:task_id>', methods=['POST'])
@login_required
def delete_task(task_id):
    db = get_db()
    db.execute('DELETE FROM tasks WHERE id = ? AND user_id = ?', (task_id, session['user_id']))
    db.commit()
    flash('Tarea eliminada.', 'info')
    return redirect(url_for('dashboard'))

@app.route('/task/toggle/<int:task_id>', methods=['POST'])
@login_required
def toggle_task(task_id):
    db = get_db()
    task = db.execute('SELECT completed FROM tasks WHERE id = ? AND user_id = ?', (task_id, session['user_id'])).fetchone()
    if not task:
        flash('Tarea no encontrada.', 'danger')
        return redirect(url_for('dashboard'))
    new = 0 if task['completed'] else 1
    db.execute('UPDATE tasks SET completed = ? WHERE id = ?', (new, task_id))
    db.commit()
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True)
