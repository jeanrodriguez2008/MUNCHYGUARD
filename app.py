import os
import uuid
from datetime import datetime, UTC, time
from functools import wraps
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

# ========================================================
# CONFIGURACIÓN DE LA APLICACIÓN Y BASE DE DATOS
# ========================================================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "munchy_secret_key_production")

base_dir = os.path.abspath(os.path.dirname(__file__))

# Conexión Dinámica: Detecta Neon PostgreSQL en Render o SQLite local
db_url = os.environ.get("DATABASE_URL")

if db_url:
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(base_dir, 'munchy_guard.db')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
    "pool_timeout": 30
}

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ========================================================
# MODELOS DE LA BASE DE DATOS (MUNCHYGUARD V20 AUDIT)
# ========================================================
class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    rol = db.Column(db.String(20), default='OPERADOR')
    nombre_completo = db.Column(db.String(120), nullable=True)
    cedula_rif = db.Column(db.String(30), nullable=True)
    correo = db.Column(db.String(100), nullable=True)
    pregunta_seguridad = db.Column(db.String(200), nullable=True)
    respuesta_seguridad = db.Column(db.String(200), nullable=True)

class Configuracion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    dias_criticos = db.Column(db.Integer, default=30)
    dias_alerta = db.Column(db.Integer, default=90)

class Producto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(30), unique=True, nullable=False)
    articulo = db.Column(db.String(100), nullable=False)
    dias_criticos = db.Column(db.Integer, default=30, nullable=False)
    dias_alerta = db.Column(db.Integer, default=90, nullable=False)
    usuario_registro = db.Column(db.String(50), default='Sistema', nullable=False)
    ultima_actualizacion = db.Column(db.DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None), onupdate=lambda: datetime.now(UTC).replace(tzinfo=None))

class Almacen(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(30), unique=True, nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    capacidad_maxima = db.Column(db.Integer, default=10000, nullable=False)
    usuario_registro = db.Column(db.String(50), default='Sistema', nullable=False)
    ultima_actualizacion = db.Column(db.DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None), onupdate=lambda: datetime.now(UTC).replace(tzinfo=None))

class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(30), unique=True, nullable=False)
    razon_social = db.Column(db.String(120), nullable=False)
    usuario_registro = db.Column(db.String(50), default='Sistema', nullable=False)
    ultima_actualizacion = db.Column(db.DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None), onupdate=lambda: datetime.now(UTC).replace(tzinfo=None))

class Vendedor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(30), unique=True, nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    estatus = db.Column(db.String(20), default='ACTIVO', nullable=False)
    usuario_registro = db.Column(db.String(50), default='Sistema', nullable=False)
    ultima_actualizacion = db.Column(db.DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None), onupdate=lambda: datetime.now(UTC).replace(tzinfo=None))

class MovimientoInventario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    id_registro_unico = db.Column(db.String(60), unique=True, nullable=False)
    tipo_operacion = db.Column(db.String(20), nullable=False)
    tipo_motivo = db.Column(db.String(40), nullable=False)    
    codigo_producto = db.Column(db.String(30), nullable=False)
    almacen_origen = db.Column(db.String(30), nullable=True)
    almacen_destino = db.Column(db.String(30), nullable=True)
    codigo_cliente = db.Column(db.String(30), nullable=True)
    codigo_vendedor = db.Column(db.String(30), nullable=True)
    numero_lote = db.Column(db.String(50), nullable=False)
    fecha_vencimiento = db.Column(db.String(10), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)          
    referencia_documento = db.Column(db.String(50), nullable=False)
    nota_despacho = db.Column(db.String(50), nullable=True)   
    fecha_sistema = db.Column(db.DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None))
    detalle_devolucion = db.Column(db.String(100), nullable=True)
    usuario_registro = db.Column(db.String(50), nullable=False)

class LogsAuditoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha_evento = db.Column(db.DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None))
    usuario = db.Column(db.String(50), nullable=False)
    rol = db.Column(db.String(20), nullable=False)
    modulo = db.Column(db.String(50), nullable=False)
    accion_detallada = db.Column(db.Text, nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Usuario, int(user_id))

# Inicialización automática
with app.app_context():
    db.create_all()
    admin_user = Usuario.query.filter_by(username='admin').first()
    if not admin_user:
        usuario_master = Usuario(
            username='admin',
            password='admin123',
            rol='ADMIN',
            nombre_completo='Administrador del Sistema',
            cedula_rif='J-000000000',
            correo='admin@alimentosmunchy.com',
            pregunta_seguridad='¿Nombre de tu primera mascota?',
            respuesta_seguridad='MUNCHY'
        )
        db.session.add(usuario_master)
        db.session.commit()

# ========================================================
# DECORADORES PARA CONTROL DE ACCESO SEGURO
# ========================================================
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.rol != 'ADMIN':
            flash("⚠️ Operación denegada: Requiere privilegios de Administrador.", "danger")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def operciones_lectura_required(roles_permitidos):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.rol not in roles_permitidos:
                flash("⚠️ Restricción de Perfil: No tienes autorización para ejecutar esta acción.", "danger")
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorator
    return decorator

# ========================================================
# LOGIC FLUX: OBTENER SALDOS Y SEMÁFORO
# ========================================================
def obtener_saldos_por_lote():
    dict_umbrales_productos = {p.codigo: {'criticos': p.dias_criticos, 'alerta': p.dias_alerta} for p in Producto.query.all()}
    movimientos = db.session.query(MovimientoInventario).order_by(MovimientoInventario.fecha_sistema.asc()).all()
    saldos = {}
    
    for m in movimientos:
        if m.tipo_operacion == 'ENTRADA':
            if m.almacen_destino:
                clave_destino = (m.codigo_producto, m.numero_lote, m.almacen_destino)
                if clave_destino not in saldos:
                    saldos[clave_destino] = {'cantidad': 0, 'fecha_vencimiento': m.fecha_vencimiento}
                saldos[clave_destino]['cantidad'] += m.cantidad
            
            if m.almacen_origen:
                clave_origen = (m.codigo_producto, m.numero_lote, m.almacen_origen)
                if clave_origen not in saldos:
                    saldos[clave_origen] = {'cantidad': 0, 'fecha_vencimiento': m.fecha_vencimiento}
                saldos[clave_origen]['cantidad'] -= m.cantidad

        elif m.tipo_operacion == 'SALIDA':
            if m.almacen_origen:
                clave_origen = (m.codigo_producto, m.numero_lote, m.almacen_origen)
                if clave_origen not in saldos:
                    saldos[clave_origen] = {'cantidad': 0, 'fecha_vencimiento': m.fecha_vencimiento}
                saldos[clave_origen]['cantidad'] -= m.cantidad
            
            if m.almacen_destino:
                clave_destino = (m.codigo_producto, m.numero_lote, m.almacen_destino)
                if clave_destino not in saldos:
                    saldos[clave_destino] = {'cantidad': 0, 'fecha_vencimiento': m.fecha_vencimiento}
                saldos[clave_destino]['cantidad'] += m.cantidad
                
    inventario_disponible = []
    fecha_actual = datetime.now(UTC).replace(tzinfo=None)

    for (prod, lote, almacen), info in saldos.items():
        if info['cantidad'] > 0:
            dias_restantes = None
            alerta_color = "verde"
            regla_sku = dict_umbrales_productos.get(prod, {'criticos': 30, 'alerta': 90})
            
            try:
                fecha_venc = datetime.strptime(info['fecha_vencimiento'], "%d/%m/%Y")
                dias_restantes = (fecha_venc - fecha_actual).days
                
                if dias_restantes <= regla_sku['criticos']:
                    alerta_color = "rojo"
                elif dias_restantes <= regla_sku['alerta']:
                    alerta_color = "amarillo"
            except:
                pass

            inventario_disponible.append({
                'codigo_producto': prod, 'numero_lote': lote, 'almacen': almacen,
                'cantidad': info['cantidad'], 'fecha_vencimiento': info['fecha_vencimiento'],
                'dias_restantes': dias_restantes, 'alerta_color': alerta_color
            })
            
    try:
        inventario_disponible.sort(key=lambda x: datetime.strptime(x['fecha_vencimiento'], "%d/%m/%Y"))
    except:
        pass
        
    return inventario_disponible

# ========================================================
# ENDPOINT DE CONCILIACIÓN AUTOMÁTICA DESDE MUNCHYPRODQR
# ========================================================
@app.route('/api/v1/conciliacion/munchyproqr', methods=['POST'])
def api_conciliacion_munchyproqr():
    try:
        data = request.get_json() or {}
        
        codigo_producto = str(data.get('codigo_producto') or '').strip().upper()
        numero_lote = str(data.get('numero_lote') or 'SIN LOTE').strip().upper()
        fecha_venc_raw = str(data.get('fecha_vencimiento') or '').strip()
        cantidad = int(data.get('cantidad', 0))
        
        # Asignación por defecto según reglas operativas de Planta Maracay
        almacen_origen = str(data.get('almacen_origen') or 'Gal-Morita').strip()
        almacen_destino = str(data.get('almacen_destino') or 'Gal-MORII').strip()
        
        num_recibo_raw = str(data.get('referencia_documento') or data.get('numero_recibo') or '').strip().upper()
        usuario_pro = str(data.get('usuario') or 'AlmacenistaProQR').strip()

        if not codigo_producto or cantidad <= 0:
            return jsonify({'success': False, 'error': 'Datos incompletos: Código de producto y cantidad son obligatorios.'}), 400

        # Formatear la fecha a DD/MM/YYYY
        fecha_vencimiento = "31/12/2099"
        if fecha_venc_raw:
            if "-" in fecha_venc_raw:
                try:
                    fecha_vencimiento = datetime.strptime(fecha_venc_raw, "%Y-%m-%d").strftime("%d/%m/%Y")
                except ValueError:
                    fecha_vencimiento = fecha_venc_raw
            else:
                fecha_vencimiento = fecha_venc_raw

        # VALIDACIÓN PREVENTIVA DE DOCUMENTO / RECIBO
        referencia_documento = num_recibo_raw if num_recibo_raw else f"REC-{numero_lote}"

        # Validar si la conciliación ya se había registrado previamente
        mov_existente = MovimientoInventario.query.filter_by(referencia_documento=referencia_documento).first()
        if mov_existente:
            return jsonify({
                'success': True,
                'message': f'El recibo/ticket N° {referencia_documento} ya se encontraba conciliado en MunchyGuardPT.',
                'id_transaccion': mov_existente.id_registro_unico
            }), 200

        # Asegurar la existencia del SKU en el maestro de Productos
        prod_obj = Producto.query.filter_by(codigo=codigo_producto).first()
        if not prod_obj:
            nuevo_prod = Producto(
                codigo=codigo_producto,
                articulo=f"PRODUCTO {codigo_producto}",
                dias_criticos=30,
                dias_alerta=90,
                usuario_registro=f"PROQR:{usuario_pro}"
            )
            db.session.add(nuevo_prod)

        # Asegurar la existencia del Almacén Receptor en el maestro de Almacenes
        obj_almacen = Almacen.query.filter_by(codigo=almacen_destino).first()
        if not obj_almacen:
            obj_almacen = Almacen(
                codigo=almacen_destino,
                nombre=f"ALMACÉN {almacen_destino}",
                capacidad_maxima=50000,
                usuario_registro=f"PROQR:{usuario_pro}"
            )
            db.session.add(obj_almacen)

        db.session.commit()

        # Validar capacidad disponible en el almacén de destino (Gal-MORII)
        saldos_actuales = obtener_saldos_por_lote()
        ocupacion_actual = sum(s['cantidad'] for s in saldos_actuales if s['almacen'] == almacen_destino)
        if (ocupacion_actual + cantidad) > obj_almacen.capacidad_maxima:
            return jsonify({
                'success': False, 
                'error': f"Capacidad excedida en el Almacén {almacen_destino} (Límite: {obj_almacen.capacidad_maxima} unds, Ocupado: {ocupacion_actual} unds)."
            }), 400

        # Crear el movimiento de entrada en el Kardex
        id_unico = f"ING-PROQR-{codigo_producto}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        nuevo_ingreso = MovimientoInventario(
            id_registro_unico=id_unico,
            tipo_operacion='ENTRADA',
            tipo_motivo='PRODUCCION INTERNA',
            codigo_producto=codigo_producto,
            almacen_origen=almacen_origen,
            almacen_destino=almacen_destino,
            numero_lote=numero_lote,
            fecha_vencimiento=fecha_vencimiento,
            cantidad=cantidad,
            referencia_documento=referencia_documento,
            usuario_registro=f"PROQR:{usuario_pro}"
        )
        
        db.session.add(nuevo_ingreso)

        # Registrar en auditoría
        log_auditoria = LogsAuditoria(
            usuario=f"PROQR:{usuario_pro}",
            rol="SISTEMA",
            modulo="CONCILIACION API",
            accion_detallada=f"Entrada automática vía API MunchyProQR. Recibo: {referencia_documento}, SKU: {codigo_producto}, Cantidad: {cantidad} unds, Origen: {almacen_origen}, Destino: {almacen_destino}."
        )
        db.session.add(log_auditoria)

        db.session.commit()

        return jsonify({
            'success': True, 
            'message': f'✓ Conciliación exitosa. SKU {codigo_producto} ingresado a {almacen_destino}. Recibo: {referencia_documento}',
            'id_transaccion': id_unico
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/lotes_disponibles', methods=['GET'])
@login_required
def api_lotes_disponibles():
    codigo_producto = request.args.get('producto', '').strip().upper()
    almacen_origen = request.args.get('almacen', '').strip().upper()
    
    if not codigo_producto or not almacen_origen:
        return jsonify([])
        
    saldos = obtener_saldos_por_lote()
    lotes_filtrados = [
        {
            'lote': s['numero_lote'],
            'cantidad': s['cantidad'],
            'vencimiento': s['fecha_vencimiento']
        }
        for s in saldos 
        if s['codigo_producto'] == codigo_producto and s['almacen'] == almacen_origen and s['cantidad'] > 0
    ]
    return jsonify(lotes_filtrados)

# ========================================================
# CONTROL DE ACCESO, REGISTRO Y RECUPERACIÓN DE CONTRASEÑA
# ========================================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        user = Usuario.query.filter_by(username=username, password=password).first()
        if user:
            login_user(user)
            return redirect(url_for('index'))
        flash('Credenciales de acceso incorrectas', 'danger')
    return render_template('login.html')

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre_completo = request.form.get('nombre_completo', '').strip()
        cedula_rif = request.form.get('cedula_rif', '').strip().upper()
        correo = request.form.get('correo', '').strip().lower()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        pregunta_seguridad = request.form.get('pregunta_seguridad', '').strip()
        respuesta_seguridad = request.form.get('respuesta_seguridad', '').strip().upper()

        if Usuario.query.filter_by(username=username).first():
            flash('❌ El nombre de usuario ya se encuentra registrado.', 'danger')
            return redirect(url_for('registro'))

        nuevo_usuario = Usuario(
            username=username,
            password=password,
            rol='OPERADOR',
            nombre_completo=nombre_completo,
            cedula_rif=cedula_rif,
            correo=correo,
            pregunta_seguridad=pregunta_seguridad,
            respuesta_seguridad=respuesta_seguridad
        )
        db.session.add(nuevo_usuario)
        db.session.commit()
        flash('✓ Registro exitoso. Ya puedes iniciar sesión con tu usuario y contraseña.', 'success')
        return redirect(url_for('login'))

    return render_template('registro.html')

@app.route('/recuperar-password', methods=['GET', 'POST'])
def recuperar_password():
    usuario_encontrado = None
    if request.method == 'POST':
        accion = request.form.get('accion')
        username = request.form.get('username', '').strip()

        if accion == 'buscar_usuario':
            user = Usuario.query.filter_by(username=username).first()
            if user and user.pregunta_seguridad:
                usuario_encontrado = user
            else:
                flash('❌ El usuario no existe o no posee pregunta de seguridad configurada.', 'danger')

        elif accion == 'restablecer':
            respuesta = request.form.get('respuesta_seguridad', '').strip().upper()
            nueva_password = request.form.get('nueva_password', '').strip()
            user = Usuario.query.filter_by(username=username).first()

            if user and user.respuesta_seguridad == respuesta:
                user.password = nueva_password
                db.session.commit()
                flash('✓ Contraseña reestablecida con éxito. Inicia sesión con tus nuevos datos.', 'success')
                return redirect(url_for('login'))
            else:
                flash('❌ La respuesta de seguridad es incorrecta.', 'danger')
                usuario_encontrado = user

    return render_template('recuperar_password.html', usuario=usuario_encontrado)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ========================================================
# CORE OPERACIONAL (TABLERO PRINCIPAL)
# ========================================================
@app.route('/')
@login_required
def index():
    config_params = Configuracion.query.first() or Configuracion(dias_criticos=30, dias_alerta=90)
    productos = Producto.query.order_by(Producto.articulo.asc()).all()
    almacenes = Almacen.query.order_by(Almacen.nombre.asc()).all()
    clientes = Cliente.query.order_by(Cliente.razon_social.asc()).all()
    vendedores = Vendedor.query.order_by(Vendedor.nombre.asc()).all()
    
    txt_buscar = request.args.get('buscar_sku', '').strip().upper()
    fecha_inicio_str = request.args.get('fecha_inicio', '')
    fecha_fin_str = request.args.get('fecha_fin', '')
    limite_str = request.args.get('limite', '10') 
    limite_saldos_str = request.args.get('limite_saldos', '10')
    
    init_dt, end_dt = None, None
    query_base = MovimientoInventario.query
    
    if fecha_inicio_str and fecha_fin_str:
        try:
            init_dt = datetime.strptime(fecha_inicio_str + " 00:00:00", "%Y-%m-%d %H:%M:%S")
            end_dt = datetime.strptime(fecha_fin_str + " 23:59:59", "%Y-%m-%d %H:%M:%S")
            query_base = query_base.filter(MovimientoInventario.fecha_sistema.between(init_dt, end_dt))
        except ValueError: 
            pass
            
    query_movimientos = query_base.order_by(MovimientoInventario.fecha_sistema.desc())
    movimientos = query_movimientos.all() if limite_str == 'TODOS' else query_movimientos.limit(int(limite_str)).all()
    
    dict_productos = {p.codigo: p.articulo for p in productos}
    dict_vendedores = {v.codigo: v.nombre for v in vendedores}
    saldos_lotes_completos = obtener_saldos_por_lote()
    
    if txt_buscar:
        saldos_filtrados_ia = []
        for s in saldos_lotes_completos:
            codigo_sku = s['codigo_producto'].upper()
            nombre_articulo = dict_productos.get(s['codigo_producto'], '').upper()
            if txt_buscar in codigo_sku or txt_buscar in nombre_articulo:
                saldos_filtrados_ia.append(s)
        saldos_lotes_completos = saldos_filtrados_ia
    
    if limite_saldos_str != 'TODOS':
        saldos_lotes = saldos_lotes_completos[:int(limite_saldos_str)]
    else:
        saldos_lotes = saldos_lotes_completos
    
    ocupacion_almacenes = {}
    for a in almacenes:
        ocupacion_almacenes[a.codigo] = {
            'nombre': a.nombre, 'maxima': a.capacidad_maxima, 'actual': 0, 'porcentaje': 0, 'disponible': a.capacidad_maxima
        }

    for s in saldos_lotes_completos:
        target_almacen = s['almacen']
        if target_almacen in ocupacion_almacenes:
            ocupacion_almacenes[target_almacen]['actual'] += s['cantidad']
            
    for cod_alm, datos in list(ocupacion_almacenes.items()):
        if datos['maxima'] > 0:
            datos['porcentaje'] = min(int((datos['actual'] / datos['maxima']) * 100), 100)
            datos['disponible'] = max(datos['maxima'] - datos['actual'], 0)

    top_dev_query = db.session.query(
        MovimientoInventario.codigo_producto, MovimientoInventario.detalle_devolucion, db.func.sum(MovimientoInventario.cantidad).label('total')
    ).filter(MovimientoInventario.tipo_operacion == 'ENTRADA', MovimientoInventario.tipo_motivo == 'DEVOLUCION')
    
    if init_dt and end_dt:
        top_dev_query = top_dev_query.filter(MovimientoInventario.fecha_sistema.between(init_dt, end_dt))
         
    top_dev = top_dev_query.group_by(MovimientoInventario.codigo_producto, MovimientoInventario.detalle_devolucion).order_by(db.desc('total')).limit(5).all()
    labels_devoluciones = [f"{dict_productos.get(d[0], d[0])} ({d[1]})" for d in top_dev]
    cantidades_devoluciones = [d[2] for d in top_dev]

    vendedores_query = db.session.query(
        MovimientoInventario.codigo_vendedor, db.func.sum(MovimientoInventario.cantidad).label('total_facturado')
    ).filter(MovimientoInventario.tipo_operacion == 'SALIDA', MovimientoInventario.tipo_motivo == 'FACTURACION', MovimientoInventario.codigo_vendedor != None)
    
    if init_dt and end_dt:
        vendedores_query = vendedores_query.filter(MovimientoInventario.fecha_sistema.between(init_dt, end_dt))
         
    top_5_vendedores_raw = vendedores_query.group_by(MovimientoInventario.codigo_vendedor).order_by(db.desc('total_facturado')).limit(5).all()

    labels_vendedores = []
    cantidades_vendedores = []

    for v_row in top_5_vendedores_raw:
        cod_vend = v_row.codigo_vendedor
        total_v = v_row.total_facturado
        nombre_vend = dict_vendedores.get(cod_vend, cod_vend)

        prod_query = db.session.query(
            MovimientoInventario.codigo_producto, db.func.sum(MovimientoInventario.cantidad).label('total_sku')
        ).filter(MovimientoInventario.tipo_operacion == 'SALIDA', MovimientoInventario.tipo_motivo == 'FACTURACION', MovimientoInventario.codigo_vendedor == cod_vend)
        
        if init_dt and end_dt:
            prod_query = prod_query.filter(MovimientoInventario.fecha_sistema.between(init_dt, end_dt))
            
        prod_estrella_row = prod_query.group_by(MovimientoInventario.codigo_producto).order_by(db.desc('total_sku')).first()

        if prod_estrella_row:
            nombre_articulo = dict_productos.get(prod_estrella_row.codigo_producto, prod_estrella_row.codigo_producto)
            labels_vendedores.append(f"{nombre_vend} [Top: {nombre_articulo}]")
        else:
            labels_vendedores.append(nombre_vend)

        cantidades_vendedores.append(total_v)

    return render_template('index.html', usuario=current_user, config_params=config_params, productos=productos, 
                           almacenes=almacenes, clientes=clientes, vendedores=vendedores, movimientos=movimientos, 
                           dict_productos=dict_productos, fecha_inicio=fecha_inicio_str, fecha_fin=fecha_fin_str, 
                           limite=limite_str, limite_saldos=limite_saldos_str, saldos_lotes=saldos_lotes, ocupacion_almacenes=ocupacion_almacenes,
                           labels_devoluciones=labels_devoluciones, cantidades_devoluciones=cantidades_devoluciones,
                           labels_vendedores=labels_vendedores, cantidades_vendedores=cantidades_vendedores,
                           buscar_sku=txt_buscar, 
                           current_date=datetime.now().strftime('%d/%m/%Y %H:%M'))

@app.route('/configuracion/parametros', methods=['POST'])
@login_required
@admin_required
def actualizar_parametros():
    config = Configuracion.query.first() or Configuracion()
    criticos_viejos = config.dias_criticos
    alertas_viejas = config.dias_alerta
    config.dias_criticos = int(request.form.get('dias_criticos', 30))
    config.dias_alerta = int(request.form.get('dias_alerta', 90))
    
    log_cambio = LogsAuditoria(usuario=current_user.username, rol=current_user.rol, modulo="CONFIGURACIÓN",
                               accion_detallada=f"Modificó parámetros del semáforo. Días Críticos: {criticos_viejos} -> {config.dias_criticos}. Días Alerta: {alertas_viejas} -> {config.dias_alerta}.")
    db.session.add(log_cambio)
    db.session.commit()
    flash('✓ Parámetros del semáforo operacional guardados con éxito.', 'success')
    return redirect(url_for('index'))

# ========================================================
# GENERADORES DE PLANTILLAS EXCEL PARA CARGA MASIVA
# ========================================================
@app.route('/operaciones/plantilla-excel-entrada', methods=['GET'])
@login_required
def plantilla_excel_entrada():
    try:
        data = [{
            'TIPO_MOTIVO': 'PRODUCCION',
            'CODIGO_PRODUCTO': 'SKU001',
            'ALMACEN_DESTINO': 'ALM01',
            'ALMACEN_ORIGEN': '',
            'NUMERO_LOTE': 'LOTE-2026-01',
            'FECHA_VENCIMIENTO': '31/12/2026',
            'CANTIDAD': 100,
            'REFERENCIA_DOCUMENTO': 'DOC-ENT-001',
            'DETALLE_DEVOLUCION': ''
        }]
        df = pd.DataFrame(data)
        file_path = os.path.join(base_dir, 'Plantilla_Carga_Masiva_Entradas.xlsx')
        df.to_excel(file_path, index=False)
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        flash(f"❌ Error al generar plantilla: {str(e)}", "danger")
        return redirect(url_for('index'))

@app.route('/operaciones/plantilla-excel-salida', methods=['GET'])
@login_required
def plantilla_excel_salida():
    try:
        data = [{
            'TIPO_MOTIVO': 'FACTURACION',
            'CODIGO_PRODUCTO': 'SKU001',
            'ALMACEN_ORIGEN': 'ALM01',
            'ALMACEN_DESTINO': '',
            'CODIGO_CLIENTE': 'CLI001',
            'CODIGO_VENDEDOR': 'VEN001',
            'NUMERO_LOTE': 'LOTE-2026-01',
            'FECHA_VENCIMIENTO': '31/12/2026',
            'CANTIDAD': 50,
            'REFERENCIA_DOCUMENTO': 'DOC-SAL-001'
        }]
        df = pd.DataFrame(data)
        file_path = os.path.join(base_dir, 'Plantilla_Carga_Masiva_Salidas.xlsx')
        df.to_excel(file_path, index=False)
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        flash(f"❌ Error al generar plantilla: {str(e)}", "danger")
        return redirect(url_for('index'))

@app.route('/operaciones/plantilla-excel-almacen', methods=['GET'])
@login_required
def plantilla_excel_almacen():
    try:
        data = [{
            'CODIGO': 'ALM01',
            'NOMBRE': 'Almacén Principal Central',
            'CAPACIDAD': 10000
        }]
        df = pd.DataFrame(data)
        file_path = os.path.join(base_dir, 'Plantilla_Carga_Masiva_Almacenes.xlsx')
        df.to_excel(file_path, index=False)
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        flash(f"❌ Error al generar plantilla: {str(e)}", "danger")
        return redirect(url_for('index'))

@app.route('/operaciones/plantilla-excel-producto', methods=['GET'])
@login_required
def plantilla_excel_producto():
    try:
        data = [{
            'CODIGO': 'SKU001',
            'NOMBRE': 'Galletas Munchy Choco 100g',
            'DIAS_CRITICOS': 30,
            'DIAS_ALERTA': 90
        }]
        df = pd.DataFrame(data)
        file_path = os.path.join(base_dir, 'Plantilla_Carga_Masiva_Productos.xlsx')
        df.to_excel(file_path, index=False)
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        flash(f"❌ Error al generar plantilla: {str(e)}", "danger")
        return redirect(url_for('index'))

@app.route('/operaciones/plantilla-excel-cliente', methods=['GET'])
@login_required
def plantilla_excel_cliente():
    try:
        data = [{
            'CODIGO': 'CLI001',
            'NOMBRE': 'Distribuidora Central C.A.'
        }]
        df = pd.DataFrame(data)
        file_path = os.path.join(base_dir, 'Plantilla_Carga_Masiva_Clientes.xlsx')
        df.to_excel(file_path, index=False)
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        flash(f"❌ Error al generar plantilla: {str(e)}", "danger")
        return redirect(url_for('index'))

@app.route('/operaciones/plantilla-excel-vendedor', methods=['GET'])
@login_required
def plantilla_excel_vendedor():
    try:
        data = [{
            'CODIGO': 'VEN001',
            'NOMBRE': 'Pedro Pérez'
        }]
        df = pd.DataFrame(data)
        file_path = os.path.join(base_dir, 'Plantilla_Carga_Masiva_Vendedores.xlsx')
        df.to_excel(file_path, index=False)
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        flash(f"❌ Error al generar plantilla: {str(e)}", "danger")
        return redirect(url_for('index'))

# ========================================================
# PLANIFICACIÓN DE DEMANDA Y REPOSICIÓN PROYECTIVA
# ========================================================
@app.route('/operaciones/ia_analisis_gerencial', methods=['POST'])
@login_required
@operciones_lectura_required(['ADMIN', 'CONSULTOR', 'GERENTE'])
def ia_analisis_gerencial():
    try:
        from datetime import datetime, timedelta

        dias_proyeccion = int(request.form.get('dias_proyeccion', 30) or 30)
        dias_rotacion = int(request.form.get('dias_rotacion', 90) or 90)

        def fmt_cant(val):
            try:
                return "{:,}".format(int(val)).replace(',', '.')
            except (ValueError, TypeError):
                return "0"

        saldos_lotes = obtener_saldos_por_lote()
        almacenes = Almacen.query.all()
        productos = Producto.query.all()
        vendedores = Vendedor.query.all()
        clientes = Cliente.query.all()
        
        dict_productos = {p.codigo: p.articulo for p in productos}
        dict_vendedores = {v.codigo: v.nombre for v in vendedores}
        dict_clientes = {c.codigo: c.razon_social for c in clientes}

        fecha_actual = datetime.now()

        movimientos_salida = MovimientoInventario.query.filter_by(tipo_operacion='SALIDA').all()
        total_general_despachado = 0
        
        conteo_rotacion = {}        
        conteo_15_dias = {}        
        conteo_cliente_cedis = {}  
        ventas_vendedor = {}       
        vendedor_cedis_sku = {}    

        for m in movimientos_salida:
            origen = m.almacen_origen
            if not origen:
                continue
            
            dias_transcurridos = (fecha_actual - m.fecha_sistema).days
            
            if dias_transcurridos <= dias_rotacion:
                sku = m.codigo_producto
                total_general_despachado += m.cantidad

                if origen not in conteo_rotacion:
                    conteo_rotacion[origen] = {}
                conteo_rotacion[origen][sku] = conteo_rotacion[origen].get(sku, 0) + m.cantidad

            if dias_transcurridos <= 15:
                sku = m.codigo_producto
                if origen not in conteo_15_dias:
                    conteo_15_dias[origen] = {}
                conteo_15_dias[origen][sku] = conteo_15_dias[origen].get(sku, 0) + m.cantidad

            if m.codigo_cliente:
                sku = m.codigo_producto
                if origen not in conteo_cliente_cedis:
                    conteo_cliente_cedis[origen] = {}
                if sku not in conteo_cliente_cedis[origen]:
                    conteo_cliente_cedis[origen][sku] = {}
                conteo_cliente_cedis[origen][sku][m.codigo_cliente] = conteo_cliente_cedis[origen][sku].get(m.codigo_cliente, 0) + m.cantidad

            if m.codigo_vendedor and m.tipo_motivo == 'FACTURACION':
                sku = m.codigo_producto
                ventas_vendedor[m.codigo_vendedor] = ventas_vendedor.get(m.codigo_vendedor, 0) + m.cantidad
                if origen not in vendedor_cedis_sku:
                    vendedor_cedis_sku[origen] = {}
                vendedor_cedis_sku[origen][sku] = vendedor_cedis_sku[origen].get(sku, 0) + m.cantidad

        lista_abc = []
        for p in productos:
            total_sku = sum(conteo_rotacion.get(a.codigo, {}).get(p.codigo, 0) for a in almacenes)
            pct = (total_sku / total_general_despachado * 100) if total_general_despachado > 0 else 0
            lista_abc.append({'codigo': p.codigo, 'porcentaje': pct, 'categoria': 'C'})
        
        lista_abc.sort(key=lambda x: x['porcentaje'], reverse=True)
        acumulado = 0
        datos_abc = {}
        for item in lista_abc:
            acumulado += item['porcentaje']
            if acumulado <= 80:
                datos_abc[item['codigo']] = 'A'
            elif acumulado <= 95:
                datos_abc[item['codigo']] = 'B'
            else:
                datos_abc[item['codigo']] = 'C'

        top_vendedores_ids = sorted(ventas_vendedor, key=ventas_vendedor.get, reverse=True)[:5]

        devoluciones_raw = db.session.query(
            MovimientoInventario.codigo_producto, MovimientoInventario.detalle_devolucion, db.func.sum(MovimientoInventario.cantidad)
        ).filter(MovimientoInventario.tipo_operacion == 'ENTRADA', MovimientoInventario.tipo_motivo == 'DEVOLUCION').group_by(
            MovimientoInventario.codigo_producto, MovimientoInventario.detalle_devolucion
        ).order_by(db.desc(db.func.sum(MovimientoInventario.cantidad))).limit(5).all()

        informe_html = f"""
        <div class="p-2 mb-3 bg-dark text-white rounded text-center">
            <h4 class="m-0 fw-bold"><i class="bi bi-cpu-fill"></i> INFORME DE PLANIFICACIÓN DE DEMANDA CON REPOSICIÓN PROYECTIVA</h4>
            <small class="text-white-50">Análisis Matemático Multi-Almacen a {dias_proyeccion} Días (Rotación de {dias_rotacion} Días)</small>
        </div>
        """

        tabla_proyectiva = ""
        listado_detallado = ""
        analisis_quiebres = ""
        direccionamiento_peps = ""

        alertas_quiebre_lista = []
        alertas_slotting_lista = []
        alertas_peps_lista = []
        alertas_seguridad_lista = []

        for alm in almacenes:
            stock_total_cedis = sum(s['cantidad'] for s in saldos_lotes if s['almacen'] == alm.codigo)
            pct_ocupacion = (stock_total_cedis / alm.capacidad_maxima * 100) if alm.capacidad_maxima > 0 else 0

            saldos_cedis_sku = {}
            for s in saldos_lotes:
                if s['almacen'] == alm.codigo:
                    saldos_cedis_sku[s['codigo_producto']] = saldos_cedis_sku.get(s['codigo_producto'], 0) + s['cantidad']

            tabla_proyectiva += f"""
            <div class="card mb-3 border-0 shadow-sm">
                <div class="card-header bg-light fw-bold text-dark p-2">
                    <i class="bi bi-building"></i> Matriz Logística: {alm.nombre} ({alm.codigo}) 
                    <span class="badge float-end {'bg-danger' if pct_ocupacion > 85 else 'bg-warning text-dark' if pct_ocupacion > 60 else 'bg-success'}">
                        Ocupación: {round(pct_ocupacion, 1)}%
                    </span>
                </div>
                <table class="table table-sm table-bordered font-monospace text-center small mb-0 align-middle" style="font-size:0.8rem;">
                    <thead class="table-secondary font-weight-bold">
                        <tr>
                            <th>SKU</th>
                            <th>Descripción</th>
                            <th>CMD ({dias_rotacion}d)</th>
                            <th>Stock Seg. (SS)</th>
                            <th>Punto Pedido (PP)</th>
                            <th>Inventario Actual</th>
                            <th>Reposición Sug. (CR)</th>
                        </tr>
                    </thead>
                    <tbody>"""

            cedis_tiene_movimiento = False
            lista_carga_cedis = []

            for prod in productos:
                total_salidas_sku = conteo_rotacion.get(alm.codigo, {}).get(prod.codigo, 0)
                cmd = round(total_salidas_sku / dias_rotacion, 2)
                inventario_actual = saldos_cedis_sku.get(prod.codigo, 0)

                if total_salidas_sku > 0 or inventario_actual > 0:
                    cedis_tiene_movimiento = True
                    
                    demanda_max_diaria = cmd * 1.5 if cmd > 0 else 10
                    ss = int((demanda_max_diaria * 8) - (cmd * 5))
                    if ss < 5: ss = 10

                    categoria_abc = datos_abc.get(prod.codigo, 'C')
                    if categoria_abc == 'A' and vendedor_cedis_sku.get(alm.codigo, {}).get(prod.codigo, 0) > 100:
                        ss = int(ss * 1.3)

                    pp = int((cmd * 5) + ss)
                    cr = int((cmd * dias_proyeccion) + ss - inventario_actual)
                    if cr < 0: cr = 0

                    tabla_proyectiva += f"""
                    <tr {'class="table-danger"' if inventario_actual <= pp and inventario_actual > 0 else 'class="table-warning"' if inventario_actual == 0 and cmd > 0 else ''}>
                        <td class="fw-bold">{prod.codigo}</td>
                        <td class="text-start text-truncate" style="max-width:140px;">{prod.articulo}</td>
                        <td>{fmt_cant(int(cmd * dias_proyeccion) / dias_rotacion)} u/d</td>
                        <td>{fmt_cant(ss)} u</td>
                        <td class="fw-bold">{fmt_cant(pp)} u</td>
                        <td class="fw-bold text-primary">{fmt_cant(inventario_actual)}</td>
                        <td class="fw-bold text-danger">{fmt_cant(cr)}</td>
                    </tr>"""

                    if cr > 0:
                        lista_carga_cedis.append(f"<li class='py-0'>📦 SKU: <strong>{prod.codigo}</strong> — Solicitar: <span class='text-danger fw-bold'>{fmt_cant(cr)} Unidades</span> <small class='text-muted'>({prod.articulo})</small></li>")

                    if inventario_actual > 0 and total_salidas_sku == 0:
                        alertas_seguridad_lista.append(f"<li>⚠️ <strong>Inventario Muerto en {alm.codigo}</strong>: SKU {prod.codigo} ocupa {fmt_cant(inventario_actual)} Unds con cero salidas registradas.</li>")

                    salidas_15 = conteo_15_dias.get(alm.codigo, {}).get(prod.codigo, 0)
                    cmd_15 = salidas_15 / 15
                    cmd_75_ant = (total_salidas_sku - salidas_15) / (dias_rotacion - 15) if (total_salidas_sku > salidas_15 and dias_rotacion > 15) else 0
                    if cmd_75_ant > 0 and ((cmd_15 - cmd_75_ant) / cmd_75_ant) > 0.30:
                        alertas_quiebre_lista.append(f"<li>🚀 <strong>Aceleración de Demanda en {alm.codigo}</strong>: SKU {prod.codigo} incrementó su rotación >30% en los últimos 15 días. Ajustar Punto de Pedido.</li>")

                    dict_clientes_sku = conteo_cliente_cedis.get(alm.codigo, {}).get(prod.codigo, {})
                    for cl_id, cant_cl in dict_clientes_sku.items():
                        if total_salidas_sku > 0 and (cant_cl / total_salidas_sku) > 0.50:
                            alertas_seguridad_lista.append(f"<li>👤 <strong>Riesgo de Dependencia en {alm.codigo}</strong>: Cliente {dict_clientes.get(cl_id, cl_id)} representa el {round((cant_cl/total_salidas_sku)*100,1)}% del consumo de {prod.codigo}.</li>")

                    for s_lote in saldos_lotes:
                        if s_lote['almacen'] == alm.codigo and s_lote['codigo_producto'] == prod.codigo:
                            did = (inventario_actual / cmd) if cmd > 0 else 999
                            if s_lote['dias_restantes'] and s_lote['dias_restantes'] > 0 and did > s_lote['dias_restantes']:
                                alertas_peps_lista.append(f"<li>🔴 <strong>Riesgo Crítico de Merma en {alm.codigo}</strong>: Lote <code>{s_lote['numero_lote']}</code> de {prod.codigo} vence en {s_lote['dias_restantes']} días pero su rotación actual tardará {round(did,1)} días en agotarse.</li>")

                    if categoria_abc == 'A' and pct_ocupacion > 85:
                        alertas_slotting_lista.append(f"<li>📌 <strong>Slotting Estratégico {alm.codigo}</strong>: SKU {prod.codigo} (Clase A) requiere reubicación prioritaria a zonas de flujo rápido para optimizar despacho.</li>")

            if not cedis_tiene_movimiento:
                tabla_proyectiva += "<tr><td colspan='7' class='text-muted py-2'>Sin saldos ni transacciones en este almacén.</td></tr>"

            tabla_proyectiva += "</tbody></table></div>"

            if lista_carga_cedis:
                listado_detallado += f"""
                <div class="col-md-6 mb-2">
                    <div class="p-2 bg-white rounded border h-100 shadow-sm" style="border-left: 4px solid #dc2626 !important;">
                        <span class="badge bg-danger mb-1"><i class="bi bi-truck"></i> Orden de Despacho: {alm.nombre}</span>
                        <ul class="mb-0 text-dark small ps-3 font-monospace">
                            {"".join(lista_carga_cedis)}
                        </ul>
                    </div>
                </div>"""

        analisis_quiebres = f"""
        <div class="row font-monospace small">
            <div class="col-md-6">
                <div class="p-3 bg-white border rounded h-100 shadow-sm">
                    <span class="badge bg-warning text-dark mb-2"><i class="bi bi-exclamation-triangle-fill"></i> ALERTAS DE COBERTURA Y MICRO-TENDENCIAS</span>
                    <ul class="ps-3 mb-0 text-secondary">
                        { "".join(alertas_quiebre_lista) if alertas_quiebre_lista else "<li>✓ Todas las sucursales operan dentro de los márgenes estables de stock de seguridad.</li>" }
                    </ul>
                </div>
            </div>
            <div class="col-md-6">
                <div class="p-3 bg-white border rounded h-100 shadow-sm">
                    <span class="badge bg-primary mb-2"><i class="bi bi-grid-3x3-gap-fill"></i> UBICACIÓN ESTRATÉGICA (SLOTTING ABC)</span>
                    <ul class="ps-3 mb-0 text-secondary">
                        { "".join(alertas_slotting_lista) if alertas_slotting_lista else "<li>✓ Distribución física de Clases A, B y C operando con fluidez en la red nacional.</li>" }
                    </ul>
                </div>
            </div>
        </div>"""

        devoluciones_html = ""
        if devoluciones_raw:
            for dev in devoluciones_raw:
                devoluciones_html += f"<li>🚨 Trazabilidad SKU <strong>{dev[0]}</strong>: {fmt_cant(dev[2])} Unidades devueltas por motivo <em class='text-danger'>'{dev[1]}'</em>. Se sugiere bloqueo preventivo de lotes en Kardex.</li>"

        direccionamiento_peps = f"""
        <div class="row font-monospace small mt-3">
            <div class="col-md-6">
                <div class="p-3 bg-white border rounded h-100 shadow-sm">
                    <span class="badge bg-danger mb-2"><i class="bi bi-hourglass-split"></i> VULNERABILIDAD PEPS Y RIESGOS DE MERMA</span>
                    <ul class="ps-3 mb-0 text-secondary">
                        { "".join(alertas_peps_lista) if alertas_peps_lista else "<li>✓ Rotación óptima. Ningún lote presenta DID superior a su fecha de vencimiento.</li>" }
                    </ul>
                </div>
            </div>
            <div class="col-md-6">
                <div class="p-3 bg-white border rounded h-100 shadow-sm">
                    <span class="badge bg-dark mb-2"><i class="bi bi-arrow-counterclockwise"></i> CALIDAD INVERSA (ALERTAS DE TRAZABILIDAD)</span>
                    <ul class="ps-3 mb-0 text-secondary">
                        { devoluciones_html if devoluciones_html else "<li>✓ Sin concentraciones atípicas de reingresos en el sistema.</li>" }
                    </ul>
                </div>
            </div>
        </div>"""

        seguridad_html = "".join(alertas_seguridad_lista) if alertas_seguridad_lista else "<li>✓ Auditoría conforme. Cero incidencias de inventario muerto o anomalías manuales de horario.</li>"

        vendedores_html = ""
        if top_vendedores_ids:
            for v_id in top_vendedores_ids:
                v_total = ventas_vendedor[v_id]
                v_nom = dict_vendedores.get(v_id, v_id)
                vendedores_html += f"<li>🏆 <strong>{v_nom}</strong>: {fmt_cant(v_total)} Unidades consolidadas en el período.</li>"

        comercial_seguridad = f"""
        <div class="row font-monospace small mt-3">
            <div class="col-md-6">
                <div class="p-3 bg-white border rounded h-100 shadow-sm">
                    <span class="badge bg-success mb-2"><i class="bi bi-graph-up-arrow"></i> RENDIMIENTO FUERZA DE VENTAS COMERCIAL</span>
                    <ul class="ps-3 mb-0 text-secondary">
                        { vendedores_html if vendedores_html else "<li>Sin transacciones comerciales registradas en el rango.</li>" }
                    </ul>
                </div>
            </div>
            <div class="col-md-6">
                <div class="p-3 bg-white border rounded h-100 shadow-sm">
                    <span class="badge bg-secondary mb-2"><i class="bi bi-shield-shaded"></i> INMOVILIZACIÓN, DEPENDENCIA Y SEGURIDAD</span>
                    <ul class="ps-3 mb-0 text-secondary">
                        { seguridad_html }
                    </ul>
                </div>
            </div>
        </div>"""

        informe_html += f"""
        <h6 class="fw-bold text-dark mt-3 mb-2"><b>1. DIAGNÓSTICO DE OCUPACIÓN Y ALERTAS DE CAPACIDAD</b></h6>
        {tabla_proyectiva}

        <h6 class="fw-bold text-dark mt-3 mb-2"><b>2. ANÁLISIS DE ROTACIÓN ABC Y MICRO-TENDENCIAS (ÚLTIMOS 15 DÍAS)</b></h6>
        {analisis_quiebres}

        <h6 class="fw-bold text-dark mt-3 mb-2"><b>3. MATRIZ DE RIESGO DE DEVOLUCIONES Y CALIDAD</b></h6>
        {direccionamiento_peps}

        <h6 class="fw-bold text-dark mt-3 mb-2"><b>4. COMPORTAMIENTO COMERCIAL Y VENDEDORES ESTRELLA</b></h6>
        {comercial_seguridad}

        <h6 class="fw-bold text-dark mt-4 mb-2"><b>5. PLAN DE REABASTECIMIENTO NACIONAL PREVENTIVO A {dias_proyeccion} DÍAS</b></h6>
        <div class="row g-2">
            {listado_detallado if listado_detallado else '<div class="col-12"><p class="text-muted font-monospace small text-center bg-white border p-3 rounded">✓ No se requiere emisión de órdenes de reabastecimiento. La red nacional cuenta con inventario suficiente.</p></div>'}
        </div>
        """

        return jsonify({'success': True, 'analisis': informe_html})

    except Exception as e:
        return jsonify({'success': False, 'error': f"Error en la compilación del reporte matemático: {str(e)}"})

# ========================================================
# OPERACIONES DE ENTRADA / INGRESO 
# ========================================================
@app.route('/operaciones/entrada', methods=['POST'])
@login_required
@operciones_lectura_required(['ADMIN', 'OPERADOR', 'RECEPTOR'])
def registrar_entrada():
    try:
        codigo_producto = request.form.get('codigo_producto', '').strip().upper()
        numero_lote = request.form.get('numero_lote', '').strip().upper()
        referencia_documento = request.form.get('referencia_documento', '').strip().upper()
        tipo_motivo = request.form.get('tipo_motivo', '').strip().upper()
        almacen_destino = request.form.get('almacen_destino', '').strip().upper()
        
        almacen_origen = None
        if tipo_motivo in ['TRASLADO', 'PRODUCCION INTERNA', 'PRODUCCION']:
            almacen_origen = request.form.get('almacen_origen', '').strip().upper()
            
        detalle_devolucion = request.form.get('detalle_devolucion', '').strip() if tipo_motivo == 'DEVOLUCION' else None
        f_venc_raw = request.form.get('fecha_vencimiento', '').strip()
        cantidad_ingreso = int(request.form.get('cantidad', 0))
        
        if not almacen_destino:
            flash("❌ Operación Inválida: Debe seleccionar un Almacén Destino real.", "danger")
            return redirect(url_for('index'))
            
        if tipo_motivo == 'TRASLADO' and not almacen_origen:
            flash(f"❌ Operación Inválida: El Almacén de Origen es obligatorio para {tipo_motivo}.", "danger")
            return redirect(url_for('index'))

        obj_almacen = Almacen.query.filter_by(codigo=almacen_destino).first()
        if obj_almacen:
            saldos_actuales = obtener_saldos_por_lote()
            ocupacion_actual = sum(s['cantidad'] for s in saldos_actuales if s['almacen'] == almacen_destino)
            if (ocupacion_actual + cantidad_ingreso) > obj_almacen.capacidad_maxima:
                flash(f"❌ Capacidad excedida en '{obj_almacen.nombre}'. (Máximo: {obj_almacen.capacidad_maxima})", "danger")
                return redirect(url_for('index'))
                
        fecha_vencimiento_procesada = datetime.strptime(f_venc_raw, "%Y-%m-%d").strftime("%d/%m/%Y") if "-" in f_venc_raw else f_venc_raw
        id_unico = f"ING-{codigo_producto}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        db.session.add(MovimientoInventario(
            id_registro_unico=id_unico, tipo_operacion='ENTRADA', tipo_motivo=tipo_motivo, 
            codigo_producto=codigo_producto, almacen_origen=almacen_origen, almacen_destino=almacen_destino, 
            detalle_devolucion=detalle_devolucion, numero_lote=numero_lote, fecha_vencimiento=fecha_vencimiento_procesada, 
            cantidad=cantidad_ingreso, referencia_documento=referencia_documento, usuario_registro=current_user.username
        ))
        db.session.commit()
        flash('✓ Ingreso por Producción/Movimiento registrado con éxito en la base de datos.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Error al registrar entrada: {str(e)}', 'danger')
    return redirect(url_for('index'))

# ========================================================
# OPERACIONES DE SALIDA / DESPACHO
# ========================================================
@app.route('/operaciones/salida', methods=['POST'])
@login_required
@operciones_lectura_required(['ADMIN', 'OPERADOR', 'DESPACHADOR'])
def registrar_salida():
    try:
        tipo_salida = request.form.get('tipo_motivo', '').strip().upper()
        codigo_producto = request.form.get('codigo_producto', '').strip().upper()
        numero_lote = request.form.get('numero_lote', '').strip().upper()
        referencia_documento = request.form.get('referencia_documento', '').strip().upper()
        
        codigo_cliente = request.form.get('codigo_cliente', '').strip().upper() if tipo_salida in ['FACTURACION', 'CONSIGNACION'] else None
        codigo_vendedor = request.form.get('codigo_vendedor', '').strip().upper() if tipo_salida == 'FACTURACION' else None
        almacen_origen = request.form.get('almacen_origen', '').strip().upper()
        almacen_destino = request.form.get('almacen_destino', '').strip().upper() if tipo_salida in ['TRASLADO', 'CONSIGNACION'] else None
        
        cantidad_a_retirar = int(request.form.get('cantidad', 0))
        
        if not almacen_origen:
            flash("❌ Operación Inválida: El Almacén de Origen es completamente obligatorio para despachar.", "danger")
            return redirect(url_for('index'))
            
        if tipo_salida in ['TRASLADO', 'CONSIGNACION'] and not almacen_destino:
            flash("❌ Operación Inválida: Debe indicar el Almacén Destino de la mercancía.", "danger")
            return redirect(url_for('index'))

        saldos_actuales = obtener_saldos_por_lote()
        lotes_del_producto = [s for s in saldos_actuales if s['codigo_producto'] == codigo_producto and s['almacen'] == almacen_origen]
        if lotes_del_producto:
            lotes_del_producto.sort(key=lambda x: datetime.strptime(x['fecha_vencimiento'], "%d/%m/%Y"))
            lote_mas_antiguo = lotes_del_producto[0]
            if numero_lote != lote_mas_antiguo['numero_lote']:
                flash(f"⚠️ Restricción PEPS: Debes despachar primero el lote '{lote_mas_antiguo['numero_lote']}' del almacén {almacen_origen}.", "danger")
                return redirect(url_for('index'))
                
        db.session.add(MovimientoInventario(
            id_registro_unico=f"DES-{codigo_producto}-{datetime.now().strftime('%Y%m%d%H%M%S')}", 
            tipo_operacion='SALIDA', tipo_motivo=tipo_salida, codigo_producto=codigo_producto, 
            almacen_origen=almacen_origen, almacen_destino=almacen_destino, codigo_cliente=codigo_cliente, 
            codigo_vendedor=codigo_vendedor, numero_lote=numero_lote, fecha_vencimiento=request.form.get('fecha_vencimiento'), 
            cantidad=cantidad_a_retirar, referencia_documento=referencia_documento, usuario_registro=current_user.username
        ))
        db.session.commit()
        flash('✓ Despacho procesado con éxito.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Error en salidas: {str(e)}', 'danger')
    return redirect(url_for('index'))

# ========================================================
# REPORTES Y CUBO ANALÍTICO POR ALMACÉN
# ========================================================
@app.route('/historial/inventario-almacen', methods=['GET'])
@login_required
@operciones_lectura_required(['ADMIN', 'OPERADOR', 'RECEPTOR', 'DESPACHADOR', 'CONSULTOR', 'GERENTE'])
def inventario_por_almacen():
    almacen_id = request.args.get('almacen_id', 'TODOS')
    saldos_lotes = obtener_saldos_por_lote()
    almacenes = Almacen.query.order_by(Almacen.nombre.asc()).all()
    dict_productos = {p.codigo: p.articulo for p in Producto.query.all()}
    
    inventario_final = []
    for s in saldos_lotes:
        if almacen_id != 'TODOS' and s['almacen'] != almacen_id: 
            continue
        inventario_final.append({
            'almacen': s['almacen'], 
            'codigo_producto': s['codigo_producto'], 
            'numero_lote': s['numero_lote'], 
            'fecha_vencimiento': s['fecha_vencimiento'], 
            'cantidad': s['cantidad'],
            'alerta_color': s['alerta_color'],
            'dias_restantes': s['dias_restantes']
        })
        
    inventario_final.sort(key=lambda x: (x['almacen'], x['codigo_producto']))
    return render_template('inventario_almacen.html', inventario=inventario_final, almacenes=almacenes, dict_productos=dict_productos, almacen_seleccionado=almacen_id)

@app.route('/historial/analisis-abc', methods=['GET'])
@login_required
@operciones_lectura_required(['ADMIN', 'OPERADOR', 'CONSULTOR', 'GERENTE'])
def analisis_abc():
    almacen_id = request.args.get('almacen_id', 'TODOS').strip().upper()
    almacenes = Almacen.query.order_by(Almacen.nombre.asc()).all()
    dict_productos = {p.codigo: p.articulo for p in Producto.query.all()}
    
    query_salidas = MovimientoInventario.query.filter_by(tipo_operacion='SALIDA')
    if almacen_id != 'TODOS':
        query_salidas = query_salidas.filter(MovimientoInventario.almacen_origen == almacen_id)
        
    movimientos_salida = query_salidas.all()
    total_general = sum(m.cantidad for m in movimientos_salida)
    
    resumen_sku = {}
    for m in movimientos_salida:
        if m.codigo_producto not in resumen_sku:
            resumen_sku[m.codigo_producto] = 0
        resumen_sku[m.codigo_producto] += m.cantidad
        
    lista_abc = []
    for codigo, cant in resumen_sku.items():
        part = (cant / total_general * 100) if total_general > 0 else 0
        lista_abc.append({
            'codigo_producto': codigo,
            'nombre_producto': dict_productos.get(codigo, 'No asignado'),
            'total_sales': cant,
            'total_outflows': cant,
            'total_salidas': cant,
            'porcentaje': part,
            'porcentaje_acumulado': 0,
            'categoria': 'C'
        })
        
    lista_abc.sort(key=lambda x: x['total_salidas'], reverse=True)
    
    acum = 0
    for item in lista_abc:
        acum += item['porcentaje']
        item['porcentaje_acumulado'] = acum
        if item['porcentaje_acumulado'] <= 80.0:
            item['categoria'] = 'A'
        elif item['porcentaje_acumulado'] <= 95.0:
            item['categoria'] = 'B'
        else:
            item['categoria'] = 'C'
            
    return render_template('analisis_abc.html', abc_datos=lista_abc, total_general=total_general, almacenes=almacenes, almacen_seleccionado=almacen_id)

# ========================================================
# MAESTROS: GESTIÓN DE PRODUCTOS Y SEMÁFORO POR SKU
# ========================================================
@app.route('/configuracion/gestion/producto', methods=['GET', 'POST'])
@login_required
@operciones_lectura_required(['ADMIN', 'OPERADOR'])
def gestion_producto_vista():
    if request.method == 'POST':
        codigo = request.form.get('codigo').strip().upper()
        articulo = request.form.get('articulo').strip()
        dias_criticos = int(request.form.get('dias_criticos', 30))
        dias_alerta = int(request.form.get('dias_alerta', 90))
        
        if Producto.query.filter_by(codigo=codigo).first():
            flash("❌ El SKU ya se encuentra registrado.", "danger")
        else:
            db.session.add(Producto(
                codigo=codigo, articulo=articulo, 
                dias_criticos=dias_criticos, dias_alerta=dias_alerta, 
                usuario_registro=current_user.username
            ))
            db.session.commit()
            flash(f"✓ SKU '{codigo}' añadido con éxito.", "success")
        return redirect(url_for('gestion_producto_vista'))
    productos = Producto.query.order_by(Producto.articulo.asc()).all()
    return render_template('gestion_producto.html', productos=productos)

@app.route('/configuracion/gestion/producto/editar/<int:id>', methods=['POST'])
@login_required
@operciones_lectura_required(['ADMIN', 'OPERADOR'])
def editar_producto_maestro(id):
    producto = Producto.query.get_or_404(id)
    producto.articulo = request.form.get('articulo').strip()
    producto.dias_criticos = int(request.form.get('dias_criticos', 30))
    producto.dias_alerta = int(request.form.get('dias_alerta', 90))
    producto.usuario_registro = current_user.username
    db.session.commit()
    flash(f"✓ SKU '{producto.codigo}' actualizado correctamente.", "success")
    return redirect(url_for('gestion_producto_vista'))

@app.route('/configuracion/gestion/producto/eliminar/<int:id>', methods=['POST'])
@login_required
@admin_required
def eliminar_producto_maestro(id):
    p = Producto.query.get_or_404(id)
    db.session.delete(p)
    db.session.commit()
    flash('✓ Producto desincorporado con éxito.', 'success')
    return redirect(url_for('gestion_producto_vista'))

# ========================================================
# MAESTROS: GESTIÓN DE VENDEDORES
# ========================================================
@app.route('/configuracion/gestion/vendedor', methods=['GET', 'POST'])
@app.route('/configuracion/gestion/vendedores', methods=['GET', 'POST'])
@login_required
@operciones_lectura_required(['ADMIN', 'OPERADOR'])
def gestion_vendedores_vista():
    if request.method == 'POST':
        codigo = request.form.get('codigo').strip().upper()
        nombre = request.form.get('nombre').strip()
        vendedor_existente = Vendedor.query.filter_by(codigo=codigo).first()
        if vendedor_existente:
            flash("❌ El código de vendedor ya se encuentra registrado.", "danger")
        else:
            db.session.add(Vendedor(codigo=codigo, nombre=nombre, estatus='ACTIVO'))
            db.session.commit()
            flash(f"✓ Vendedor '{nombre}' registrado con éxito.", "success")
        return redirect(url_for('gestion_vendedores_vista'))
    vendedores = Vendedor.query.order_by(Vendedor.nombre.asc()).all()
    return render_template('gestion_vendedor.html', vendedores=vendedores)

@app.route('/configuracion/gestion/vendedor/eliminar/<int:id>', methods=['POST'])
@login_required
@admin_required
def eliminar_vendedor_maestro(id):
    v = Vendedor.query.get_or_404(id)
    db.session.delete(v)
    db.session.commit()
    flash('✓ Vendedor desincorporado con éxito.', 'success')
    return redirect(url_for('gestion_vendedores_vista'))

@app.route('/configuracion/gestion/vendedor')
@login_required
def gestion_vendedor_vista():
    return redirect(url_for('gestion_vendedores_vista'))

# ========================================================
# MAESTROS: GESTIÓN DE ALMACENES
# ========================================================
@app.route('/configuracion/maestro/almacenes', methods=['GET', 'POST'])
@login_required
@admin_required
def gestion_almacen_vista():
    if request.method == 'POST':
        id_almacen = request.form.get('id_almacen')
        codigo_raw = request.form.get('codigo')
        nombre_raw = request.form.get('nombre')
        capacidad = request.form.get('capacidad_maxima', '10000')

        codigo = codigo_raw.strip().upper() if codigo_raw else ""
        nombre = nombre_raw.strip() if nombre_raw else ""

        try:
            capacidad_int = int(capacidad)
        except ValueError:
            capacidad_int = 10000

        if id_almacen:
            a = Almacen.query.get_or_404(int(id_almacen))
            a.capacidad_maxima = capacidad_int
            a.usuario_registro = current_user.username
            db.session.commit()
            flash(f"✓ Capacidad del almacén [{a.codigo}] actualizada a {capacidad_int} Unds.", "success")
            return redirect(url_for('gestion_almacen_vista'))

        if not codigo or not nombre:
            flash("❌ El código y el nombre del almacén son campos obligatorios.", "danger")
            return redirect(url_for('gestion_almacen_vista'))

        existe = Almacen.query.filter_by(codigo=codigo).first()
        if existe:
            flash(f"❌ El código de almacén '{codigo}' ya existe en el maestro.", "danger")
            return redirect(url_for('gestion_almacen_vista'))

        nuevo = Almacen(codigo=codigo, nombre=nombre, capacidad_maxima=capacidad_int, usuario_registro=current_user.username)
        db.session.add(nuevo)
        db.session.commit()
        flash(f"✓ Almacén [{codigo}] guardado con éxito.", "success")
        return redirect(url_for('gestion_almacen_vista'))

    almacenes = Almacen.query.order_by(Almacen.codigo.asc()).all()
    return render_template('gestion_almacen.html', almacenes=almacenes)

@app.route('/configuracion/gestion/almacen/eliminar/<int:id>', methods=['POST'])
@login_required
@admin_required
def eliminar_almacen_maestro(id):
    a = Almacen.query.get_or_404(id)
    db.session.delete(a)
    db.session.commit()
    flash('✓ Almacén desincorporado con éxito.', 'success')
    return redirect(url_for('gestion_almacen_vista'))

# ========================================================
# MAESTROS: GESTIÓN DE CLIENTES
# ========================================================
@app.route('/configuracion/gestion/clientes', methods=['GET', 'POST'])
@login_required
@operciones_lectura_required(['ADMIN', 'OPERADOR'])
def gestion_cliente_vista():
    if request.method == 'POST':
        codigo = request.form.get('codigo').strip().upper()
        razon_social = request.form.get('razon_social').strip()
        if Cliente.query.filter_by(codigo=codigo).first():
            flash("❌ El código de cliente ya existe.", "danger")
        else:
            db.session.add(Cliente(codigo=codigo, razon_social=razon_social, usuario_registro=current_user.username))
            db.session.commit()
            flash('✓ Cliente guardado con éxito.', 'success')
        return redirect(url_for('gestion_cliente_vista'))
    clientes = Cliente.query.order_by(Cliente.razon_social.asc()).all()
    return render_template('gestion_cliente.html', clientes=clientes)

@app.route('/configuracion/gestion/cliente/eliminar/<int:id>', methods=['POST'])
@login_required
@admin_required
def eliminar_cliente_maestro(id):
    c = Cliente.query.get_or_404(id)
    db.session.delete(c)
    db.session.commit()
    flash('✓ Cliente desincorporado con éxito.', 'success')
    return redirect(url_for('gestion_cliente_vista'))

# ========================================================
# CARGA MASIVA EXCEL
# ========================================================
@app.route('/operaciones/importar-excel', methods=['POST'])
@login_required
@operciones_lectura_required(['ADMIN', 'OPERADOR'])
def importar_excel():
    tipo_maestro = request.form.get('tipo_maestro', '').strip().lower()
    file = request.files.get('archivo_excel')
    
    if not file or file.filename == '':
        flash("❌ Archivo no seleccionado o corrupto.", "danger")
        return redirect(url_for('index'))
        
    try:
        df = pd.read_excel(file)
        df.columns = df.columns.str.strip().str.upper()
        df.columns = df.columns.str.replace('Ó', 'O').str.replace('É', 'E').str.replace('Á', 'A').str.replace('Í', 'I').str.replace('Ú', 'U')
        
        filas_datos = df.to_dict(orient='records')
        contador = 0
        
        if tipo_maestro == 'entrada':
            for fila in filas_datos:
                tipo_motivo = str(fila.get('TIPO_MOTIVO') or '').strip().upper()
                codigo_producto = str(fila.get('CODIGO_PRODUCTO') or '').strip().upper()
                almacen_destino = str(fila.get('ALMACEN_DESTINO') or '').strip().upper()
                almacen_origen = str(fila.get('ALMACEN_ORIGEN') or '').strip().upper() if fila.get('ALMACEN_ORIGEN') else None
                numero_lote = str(fila.get('NUMERO_LOTE') or '').strip().upper()
                fecha_venc = str(fila.get('FECHA_VENCIMIENTO') or '').strip()
                cantidad = int(fila.get('CANTIDAD', 0))
                ref_doc = str(fila.get('REFERENCIA_DOCUMENTO') or '').strip().upper()
                det_dev = str(fila.get('DETALLE_DEVOLUCION') or '').strip() if tipo_motivo == 'DEVOLUCION' else None
                
                if codigo_producto and almacen_destino and cantidad > 0:
                    id_unico = f"ING-{codigo_producto}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
                    db.session.add(MovimientoInventario(
                        id_registro_unico=id_unico, tipo_operacion='ENTRADA', tipo_motivo=tipo_motivo,
                        codigo_producto=codigo_producto, almacen_origen=almacen_origen, almacen_destino=almacen_destino,
                        detalle_devolucion=det_dev, numero_lote=numero_lote, fecha_vencimiento=fecha_venc,
                        cantidad=cantidad, referencia_documento=ref_doc, usuario_registro=current_user.username
                    ))
                    contador += 1
            db.session.commit()
            flash(f"✓ Carga Masiva Exitosa: Se procesaron {contador} Entradas.", "success")
            return redirect(url_for('index'))

        elif tipo_maestro == 'salida':
            for fila in filas_datos:
                tipo_motivo = str(fila.get('TIPO_MOTIVO') or '').strip().upper()
                codigo_producto = str(fila.get('CODIGO_PRODUCTO') or '').strip().upper()
                almacen_origen = str(fila.get('ALMACEN_ORIGEN') or '').strip().upper()
                almacen_destino = str(fila.get('ALMACEN_DESTINO') or '').strip().upper() if fila.get('ALMACEN_DESTINO') else None
                codigo_cliente = str(fila.get('CODIGO_CLIENTE') or '').strip().upper() if fila.get('CODIGO_CLIENTE') else None
                codigo_vendedor = str(fila.get('CODIGO_VENDEDOR') or '').strip().upper() if fila.get('CODIGO_VENDEDOR') else None
                numero_lote = str(fila.get('NUMERO_LOTE') or '').strip().upper()
                fecha_venc = str(fila.get('FECHA_VENCIMIENTO') or '').strip()
                cantidad = int(fila.get('CANTIDAD', 0))
                ref_doc = str(fila.get('REFERENCIA_DOCUMENTO') or '').strip().upper()
                
                if codigo_producto and almacen_origen and cantidad > 0:
                    id_unico = f"DES-{codigo_producto}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
                    db.session.add(MovimientoInventario(
                        id_registro_unico=id_unico, tipo_operacion='SALIDA', tipo_motivo=tipo_motivo,
                        codigo_producto=codigo_producto, almacen_origen=almacen_origen, almacen_destino=almacen_destino,
                        codigo_cliente=codigo_cliente, codigo_vendedor=codigo_vendedor, numero_lote=numero_lote,
                        fecha_vencimiento=fecha_venc, cantidad=cantidad, referencia_documento=ref_doc,
                        usuario_registro=current_user.username
                    ))
                    contador += 1
            db.session.commit()
            flash(f"✓ Carga Masiva Exitosa: Se procesaron {contador} Despachos/Salidas.", "success")
            return redirect(url_for('index'))

        elif tipo_maestro == 'vendedor':
            for fila in filas_datos:
                codigo = str(fila.get('CODIGO') or '').strip().upper()
                nombre = str(fila.get('NOMBRE') or '').strip()
                if codigo and codigo != 'NAN' and nombre and nombre != 'NAN':
                    existe = Vendedor.query.filter_by(codigo=codigo).first()
                    if not existe:
                        db.session.add(Vendedor(codigo=codigo, nombre=nombre, estatus='ACTIVO', usuario_registro=current_user.username))
                        contador += 1
            db.session.commit()
            flash(f"✓ Carga Masiva Exitosa: Se registraron {contador} Vendedores.", "success")
            return redirect(url_for('gestion_vendedores_vista'))

        elif tipo_maestro == 'almacen':
            for fila in filas_datos:
                codigo = str(fila.get('CODIGO') or '').strip().upper()
                nombre = str(fila.get('NOMBRE') or '').strip()
                capacidad = int(fila.get('CAPACIDAD', 10000))
                if codigo and codigo != 'NAN' and nombre and nombre != 'NAN':
                    existe = Almacen.query.filter_by(codigo=codigo).first()
                    if not existe:
                        db.session.add(Almacen(codigo=codigo, nombre=nombre, capacidad_maxima=capacidad, usuario_registro=current_user.username))
                        contador += 1
            db.session.commit()
            flash(f"✓ Carga Masiva Exitosa: Se registraron {contador} Almacenes.", "success")
            return redirect(url_for('gestion_almacen_vista'))
            
        elif tipo_maestro == 'producto':
            for fila in filas_datos:
                codigo = str(fila.get('CODIGO') or '').strip().upper()
                articulo = str(fila.get('NOMBRE') or fila.get('ARTICULO') or '').strip()
                dias_criticos = int(fila.get('DIAS_CRITICOS', 30))
                dias_alerta = int(fila.get('DIAS_ALERTA', 90))
                if codigo and codigo != 'NAN' and articulo and articulo != 'NAN':
                    existe = Producto.query.filter_by(codigo=codigo).first()
                    if not existe:
                        db.session.add(Producto(codigo=codigo, articulo=articulo, dias_criticos=dias_criticos, dias_alerta=dias_alerta, usuario_registro=current_user.username))
                        contador += 1
            db.session.commit()
            flash(f"✓ Carga Masiva Exitosa: Se registraron {contador} SKUs.", "success")
            return redirect(url_for('gestion_producto_vista'))
            
        elif tipo_maestro == 'cliente':
            for fila in filas_datos:
                codigo = str(fila.get('CODIGO') or '').strip().upper()
                razon_social = str(fila.get('NOMBRE') or fila.get('RAZON_SOCIAL') or '').strip()
                if codigo and codigo != 'NAN' and razon_social and razon_social != 'NAN':
                    existe = Cliente.query.filter_by(codigo=codigo).first()
                    if not existe:
                        db.session.add(Cliente(codigo=codigo, razon_social=razon_social, usuario_registro=current_user.username))
                        contador += 1
            db.session.commit()
            flash(f"✓ Carga Masiva Exitosa: Se registraron {contador} Clientes.", "success")
            return redirect(url_for('gestion_cliente_vista'))
            
    except Exception as e:
        db.session.rollback()
        flash(f"❌ Error procesando matriz Excel: {str(e)}", "danger")
    return redirect(url_for('index'))

# ========================================================
# EXPORTACIONES ADICIONALES Y KARDEX
# ========================================================
@app.route('/operaciones/exportar-seleccion', methods=['POST'])
@login_required
def exportar_seleccion():
    try:
        f_inicio = request.form.get('fecha_inicio_exp', '')
        f_fin = request.form.get('fecha_fin_exp', '')
        limite = request.form.get('limite_exp', '10')
        
        query = MovimientoInventario.query
        if f_inicio and f_fin:
            dt_i = datetime.strptime(f_inicio + " 00:00:00", "%Y-%m-%d %H:%M:%S")
            dt_f = datetime.strptime(f_fin + " 23:59:59", "%Y-%m-%d %H:%M:%S")
            query = query.filter(MovimientoInventario.fecha_sistema.between(dt_i, dt_f))
            
        query = query.order_by(MovimientoInventario.fecha_sistema.desc())
        movs = query.all() if limite == 'TODOS' else query.limit(int(limite)).all()
        dict_p = {p.codigo: p.articulo for p in Producto.query.all()}
        
        data = []
        for m in movs:
            data.append({
                'ID Registro Único': m.id_registro_unico,
                'Fecha Sistema': m.fecha_sistema.strftime('%d/%m/%Y %H:%M'),
                'Tipo Operación': m.tipo_operacion,
                'Tipo Motivo': m.tipo_motivo,
                'Detalle Devolución': m.detalle_devolucion or '',
                'Código Producto': m.codigo_producto,
                'Descripción Producto': dict_p.get(m.codigo_producto, '--'),
                'Almacén Origen': m.almacen_origen or '',
                'Almacén Destino': m.almacen_destino or '',
                'Lote': m.numero_lote,
                'Fecha Vencimiento': m.fecha_vencimiento,
                'Cantidad (Unds)': m.cantidad,
                'Referencia Documento': m.referencia_documento,
                'Usuario Registro': m.usuario_registro
            })
            
        df = pd.DataFrame(data)
        out_path = os.path.join(base_dir, 'movimientos_filtrados.xlsx')
        df.to_excel(out_path, index=False)
        return send_file(out_path, as_attachment=True)
    except Exception as e:
        flash(f"❌ Error al exportar Excel: {str(e)}", "danger")
        return redirect(url_for('index'))

@app.route('/operaciones/eliminar-movimiento/<int:id>', methods=['POST'])
@login_required
@admin_required
def eliminar_movimiento_kardex(id):
    m = MovimientoInventario.query.get_or_404(id)
    db.session.delete(m)
    db.session.commit()
    flash('✓ Traza histórica eliminada correctamente del Kardex.', 'success')
    return redirect(url_for('index'))

# ========================================================
# REPORTES: TRAZABILIDAD DE LOTES Y AUDITORÍA POR FECHA
# ========================================================
@app.route('/historial/trazabilidad-lote', methods=['GET'])
@login_required
def trazabilidad_lote():
    sku_buscado = request.args.get('sku', '').strip()
    lote_buscado = request.args.get('lote', '').strip()
    almacen_query = request.args.get('almacen', '').strip()
    fecha_inicio_str = request.args.get('fecha_inicio', '').strip()
    fecha_fin_str = request.args.get('fecha_fin', '').strip()

    if fecha_inicio_str and not fecha_fin_str:
        fecha_fin_str = fecha_inicio_str
    elif fecha_fin_str and not fecha_inicio_str:
        fecha_inicio_str = fecha_fin_str

    movimientos = []
    auditoria = None

    q = MovimientoInventario.query

    if sku_buscado:
        q = q.filter(MovimientoInventario.codigo_producto.ilike(f"%{sku_buscado}%"))
    if lote_buscado:
        q = q.filter(MovimientoInventario.numero_lote.ilike(f"%{lote_buscado}%"))
    if almacen_query:
        q = q.filter((MovimientoInventario.almacen_origen == almacen_query) | (MovimientoInventario.almacen_destino == almacen_query))

    if fecha_inicio_str and fecha_fin_str and (sku_buscado or almacen_query or lote_buscado):
        try:
            f_inicio_dt = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
            f_fin_dt = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
            
            inicio_rango = datetime.combine(f_inicio_dt, time.min)
            fin_rango = datetime.combine(f_fin_dt, time.max)

            q_prev = MovimientoInventario.query.filter(MovimientoInventario.fecha_sistema < inicio_rango)
            if sku_buscado:
                q_prev = q_prev.filter(MovimientoInventario.codigo_producto.ilike(f"%{sku_buscado}%"))
            if lote_buscado:
                q_prev = q_prev.filter(MovimientoInventario.numero_lote.ilike(f"%{lote_buscado}%"))
            if almacen_query:
                q_prev = q_prev.filter((MovimientoInventario.almacen_origen == almacen_query) | (MovimientoInventario.almacen_destino == almacen_query))

            movs_previos = q_prev.all()
            
            saldo_inicial = 0
            for m in movs_previos:
                if almacen_query:
                    if m.almacen_destino == almacen_query:
                        saldo_inicial += m.cantidad
                    if m.almacen_origen == almacen_query:
                        saldo_inicial -= m.cantidad
                else:
                    if m.tipo_operacion == 'ENTRADA':
                        saldo_inicial += m.cantidad
                    elif m.tipo_operacion == 'SALIDA':
                        saldo_inicial -= m.cantidad

            q_rango = q.filter(MovimientoInventario.fecha_sistema >= inicio_rango, MovimientoInventario.fecha_sistema <= fin_rango)
            movimientos_rango = q_rango.order_by(MovimientoInventario.fecha_sistema.asc()).all()

            entradas_periodo = 0
            salidas_periodo = 0

            for m in movimientos_rango:
                if almacen_query:
                    if m.almacen_destino == almacen_query:
                        entradas_periodo += m.cantidad
                    if m.almacen_origen == almacen_query:
                        salidas_periodo += m.cantidad
                else:
                    if m.tipo_operacion == 'ENTRADA':
                        entradas_periodo += m.cantidad
                    elif m.tipo_operacion == 'SALIDA':
                        salidas_periodo -= m.cantidad

            saldo_final = saldo_inicial + entradas_periodo - salidas_periodo

            texto_lapso = f"del {f_inicio_dt.strftime('%d/%m/%Y')} al {f_fin_dt.strftime('%d/%m/%Y')}" if fecha_inicio_str != fecha_fin_str else f"al {f_inicio_dt.strftime('%d/%m/%Y')}"

            auditoria = {
                'texto_lapso': texto_lapso,
                'saldo_inicial': saldo_inicial,
                'entradas_dia': entradas_periodo,
                'salidas_dia': salidas_periodo,
                'saldo_final': saldo_final
            }

            movimientos = movimientos_rango

        except ValueError:
            movimientos = q.order_by(MovimientoInventario.fecha_sistema.desc()).all()
    else:
        movimientos = q.order_by(MovimientoInventario.fecha_sistema.desc()).all()

    almacenes = Almacen.query.all()
    productos_lista = Producto.query.all()
    movimientos_lista = MovimientoInventario.query.all()
    dict_productos = {p.codigo: p.articulo for p in productos_lista}

    return render_template('trazabilidad.html',
                           movimientos=movimientos,
                           auditoria=auditoria,
                           sku_buscado=sku_buscado,
                           lote_buscado=lote_buscado,
                           almacen_query=almacen_query,
                           fecha_inicio=fecha_inicio_str,
                           fecha_fin=fecha_fin_str,
                           almacenes=almacenes,
                           productos_lista=productos_lista,
                           movimientos_lista=movimientos_lista,
                           dict_productos=dict_productos)

# ========================================================
# GESTIÓN Y CAMBIO DE ROLES DE USUARIOS
# ========================================================
@app.route('/configuracion/gestion/usuarios', methods=['GET', 'POST'])
@login_required
@admin_required
def gestion_usuarios():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        rol = request.form.get('rol', '').strip().upper()
        
        if Usuario.query.filter_by(username=username).first():
            flash('❌ El nombre de usuario ya está en uso.', 'danger')
        else:
            db.session.add(Usuario(username=username, password=password, rol=rol))
            db.session.commit()
            flash('✓ Usuario del sistema registrado con éxito.', 'success')
        return redirect(url_for('gestion_usuarios'))
    usuarios = Usuario.query.all()
    return render_template('gestion_usuarios.html', usuarios=usuarios)

@app.route('/configuracion/usuarios/cambiar-rol/<int:id>', methods=['POST'])
@login_required
@admin_required
def cambiar_rol_usuario(id):
    u = Usuario.query.get_or_404(id)
    nuevo_rol = request.form.get('rol', '').strip().upper()
    if nuevo_rol in ['ADMIN', 'OPERADOR', 'RECEPTOR', 'DESPACHADOR', 'CONSULTOR', 'GERENTE']:
        u.rol = nuevo_rol
        db.session.commit()
        flash(f"✓ Rol de '{u.username}' actualizado a {nuevo_rol}.", 'success')
    else:
        flash('❌ Rol no válido.', 'danger')
    return redirect(url_for('gestion_usuarios'))

@app.route('/configuracion/usuarios/eliminar/<int:id>', methods=['POST'])
@login_required
@admin_required
def eliminar_usuario(id):
    if current_user.id == id:
        flash('❌ Operación Inválida: No puedes eliminar tu propia sesión activa.', 'danger')
        return redirect(url_for('gestion_usuarios'))
    u = Usuario.query.get_or_404(id)
    db.session.delete(u)
    db.session.commit()
    flash('✓ Acceso de usuario revocado con éxito.', 'success')
    return redirect(url_for('gestion_usuarios'))

# ========================================================
# ELIMINACIÓN MASIVA POR LOTE
# ========================================================
@app.route('/configuracion/eliminar-multiple', methods=['POST'])
@app.route('/configuracion/depuracion-masiva', methods=['POST'])
@login_required
@admin_required
def eliminar_multiple():
    tipo = request.form.get('tipo_maestro', '').strip().lower()
    ids = request.form.getlist('registro_ids') or request.form.getlist('registros_eliminar')
    contador = 0
    if not ids:
        flash("⚠️ No seleccionó líneas para remover.", "warning")
        return redirect(request.referrer or url_for('index'))
    try:
        if tipo == 'almacen':
            for r_id in ids:
                item = db.session.get(Almacen, int(r_id))
                if item:
                    db.session.delete(item)
                    contador += 1
            flash(f"✓ Se eliminaron {contador} Almacenes de forma masiva.", "success")
        elif tipo == 'producto':
            for r_id in ids:
                item = db.session.get(Producto, int(r_id))
                if item:
                    db.session.delete(item)
                    contador += 1
            flash(f"✓ Se eliminaron {contador} Productos del maestro de forma masiva.", "success")
        elif tipo == 'cliente':
            for r_id in ids:
                item = db.session.get(Cliente, int(r_id))
                if item:
                    db.session.delete(item)
                    contador += 1
            flash(f"✓ Se eliminaron {contador} Clientes de forma masiva.", "success")
        elif tipo == 'vendedor':
            for r_id in ids:
                item = db.session.get(Vendedor, int(r_id))
                if item:
                    db.session.delete(item)
                    contador += 1
            flash(f"✓ Se eliminaron {contador} Vendedores de forma masiva.", "success")

        log_masivo = LogsAuditoria(usuario=current_user.username, rol=current_user.rol, modulo="BORRADO MASIVO", 
                                   accion_detallada=f"Ejecutó depuración por lotes en el maestro: '{tipo}'. Removió {contador} IDs de manera irreversible.")
        db.session.add(log_masivo)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f"❌ Error en depuración masiva: {str(e)}", "danger")
    return redirect(request.referrer or url_for('index'))

@app.route('/informe/acerca-de')
@login_required
def acerca_de_munchyguard():
    return render_template('acerca_de.html')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)