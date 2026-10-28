// Lógica de la Edge Function «admin-usuarios», sin dependencias de Supabase
// para poder probarla con un backend falso (ver manejador.test.ts).
//
// Acciones (POST, JSON, con el JWT de un administrador activo):
//   { accion: "crear", email, password, nombre, rol }
//   { accion: "cambiar_rol", usuario_id, rol }
//   { accion: "cambiar_estado", usuario_id, activo }
//   { accion: "restablecer_password", usuario_id, password }
// Respuesta: { ok: true, usuario_id } o { error, codigo } con su estado HTTP.

export const ROLES_ASIGNABLES = ["admin", "trabajador"] as const;
export type RolAsignable = (typeof ROLES_ASIGNABLES)[number];

// Bloqueo en Auth hasta que un administrador reactive la cuenta (~100 años).
export const DURACION_BLOQUEO = "876000h";

// Misma política que app/core/validaciones.py.
const LONGITUD_MINIMA_PASSWORD = 8;
const LONGITUD_MAXIMA_PASSWORD = 72; // límite de bcrypt
const PATRON_EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const PATRON_UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export interface Perfil {
  role: string;
  activo: boolean;
  email: string;
}

export interface Actor {
  id: string;
  email: string | null;
}

export interface EntradaAuditoria {
  actor_id: string;
  actor_email: string | null;
  accion: string;
  entidad: string;
  entidad_id: string;
  detalle: Record<string, unknown>;
}

export interface Backend {
  usuarioDelToken(jwt: string): Promise<Actor | null>;
  perfil(id: string): Promise<Perfil | null>;
  crearUsuarioAuth(email: string, password: string, nombre: string): Promise<string>;
  eliminarUsuarioAuth(id: string): Promise<void>;
  crearPerfil(id: string, campos: Record<string, unknown>): Promise<void>;
  actualizarPerfil(id: string, campos: Record<string, unknown>): Promise<void>;
  actualizarUsuarioAuth(
    id: string,
    atributos: { password?: string; ban_duration?: string },
  ): Promise<void>;
  auditar(entrada: EntradaAuditoria): Promise<void>;
}

export class ErrorHttp extends Error {
  constructor(
    readonly status: number,
    readonly codigo: string,
    mensaje: string,
  ) {
    super(mensaje);
  }
}

type Cuerpo = Record<string, unknown>;
type Resultado = { ok: true; usuario_id: string; sin_cambios?: boolean };

function responder(status: number, cuerpo: unknown): Response {
  return new Response(JSON.stringify(cuerpo), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}

// Validación -------------------------------------------------------------------

function texto(cuerpo: Cuerpo, campo: string, maximo = 200): string {
  const valor = cuerpo[campo];
  if (typeof valor !== "string" || !valor.trim()) {
    throw new ErrorHttp(400, "dato_invalido", `Falta el campo «${campo}»`);
  }
  if (valor.length > maximo) {
    throw new ErrorHttp(400, "dato_invalido", `El campo «${campo}» es demasiado largo`);
  }
  return valor.trim();
}

export function validarPassword(valor: unknown): string {
  if (
    typeof valor !== "string" ||
    valor.length < LONGITUD_MINIMA_PASSWORD ||
    valor.length > LONGITUD_MAXIMA_PASSWORD ||
    !/[A-Za-z]/.test(valor) ||
    !/\d/.test(valor)
  ) {
    throw new ErrorHttp(
      400,
      "password_debil",
      `La contraseña debe tener entre ${LONGITUD_MINIMA_PASSWORD} y ` +
        `${LONGITUD_MAXIMA_PASSWORD} caracteres e incluir letras y números`,
    );
  }
  return valor;
}

function validarEmail(cuerpo: Cuerpo): string {
  const email = texto(cuerpo, "email", 254).toLowerCase();
  if (!PATRON_EMAIL.test(email)) {
    throw new ErrorHttp(400, "dato_invalido", "El correo no es válido");
  }
  return email;
}

function validarRol(valor: unknown): RolAsignable {
  if (!ROLES_ASIGNABLES.includes(valor as RolAsignable)) {
    throw new ErrorHttp(400, "dato_invalido", "El rol debe ser «admin» o «trabajador»");
  }
  return valor as RolAsignable;
}

function validarUsuarioId(valor: unknown): string {
  if (typeof valor !== "string" || !PATRON_UUID.test(valor)) {
    throw new ErrorHttp(400, "dato_invalido", "Identificador de usuario no válido");
  }
  return valor.toLowerCase();
}

// Autorización -----------------------------------------------------------------

async function autenticarAdmin(req: Request, backend: Backend): Promise<Actor> {
  const cabecera = req.headers.get("Authorization") ?? "";
  const jwt = cabecera.match(/^Bearer\s+(.+)$/i)?.[1];
  if (!jwt) {
    throw new ErrorHttp(401, "no_autenticado", "Falta el token de sesión");
  }
  const actor = await backend.usuarioDelToken(jwt);
  if (!actor) {
    throw new ErrorHttp(401, "sesion_invalida", "La sesión no es válida o expiró");
  }
  const perfil = await backend.perfil(actor.id);
  if (perfil?.role !== "admin" || !perfil.activo) {
    throw new ErrorHttp(403, "no_autorizado", "Solo un administrador activo puede gestionar usuarios");
  }
  return actor;
}

async function perfilExistente(backend: Backend, id: string): Promise<Perfil> {
  const perfil = await backend.perfil(id);
  if (!perfil) {
    throw new ErrorHttp(404, "no_encontrado", "Usuario no encontrado");
  }
  return perfil;
}

function noSobreSiMismo(actor: Actor, id: string, mensaje: string): void {
  if (actor.id === id) {
    throw new ErrorHttp(409, "propio_usuario", mensaje);
  }
}

// Acciones ---------------------------------------------------------------------

async function crear(backend: Backend, actor: Actor, cuerpo: Cuerpo): Promise<Resultado> {
  const email = validarEmail(cuerpo);
  const password = validarPassword(cuerpo.password);
  const nombre = texto(cuerpo, "nombre", 120);
  const rol = validarRol(cuerpo.rol);

  const id = await backend.crearUsuarioAuth(email, password, nombre);
  try {
    await backend.crearPerfil(id, { email, full_name: nombre, role: rol, activo: true });
  } catch (error) {
    // Sin perfil la cuenta quedaría huérfana: se deshace el alta en Auth.
    await backend.eliminarUsuarioAuth(id).catch((e) =>
      console.error("No se pudo deshacer el alta en Auth", id, e)
    );
    throw error;
  }

  await backend.auditar({
    actor_id: actor.id,
    actor_email: actor.email,
    accion: "usuario.crear",
    entidad: "usuario",
    entidad_id: id,
    detalle: { email, nombre, rol },
  });
  return { ok: true, usuario_id: id };
}

async function cambiarRol(backend: Backend, actor: Actor, cuerpo: Cuerpo): Promise<Resultado> {
  const id = validarUsuarioId(cuerpo.usuario_id);
  const rol = validarRol(cuerpo.rol);
  noSobreSiMismo(actor, id, "No puedes cambiar tu propio rol");

  const perfil = await perfilExistente(backend, id);
  if (perfil.role === rol) {
    return { ok: true, usuario_id: id, sin_cambios: true };
  }

  await backend.actualizarPerfil(id, { role: rol });
  await backend.auditar({
    actor_id: actor.id,
    actor_email: actor.email,
    accion: "usuario.cambiar_rol",
    entidad: "usuario",
    entidad_id: id,
    detalle: { email: perfil.email, rol_anterior: perfil.role, rol_nuevo: rol },
  });
  return { ok: true, usuario_id: id };
}

async function cambiarEstado(backend: Backend, actor: Actor, cuerpo: Cuerpo): Promise<Resultado> {
  const id = validarUsuarioId(cuerpo.usuario_id);
  if (typeof cuerpo.activo !== "boolean") {
    throw new ErrorHttp(400, "dato_invalido", "El campo «activo» debe ser verdadero o falso");
  }
  const activo = cuerpo.activo;
  noSobreSiMismo(actor, id, "No puedes desactivar tu propia cuenta");

  const perfil = await perfilExistente(backend, id);
  if (perfil.activo === activo) {
    return { ok: true, usuario_id: id, sin_cambios: true };
  }

  // Primero el perfil: RLS corta el acceso al instante y el trigger de la base
  // impide dejar el sistema sin administradores.
  await backend.actualizarPerfil(id, { activo });
  try {
    // El bloqueo en Auth impide iniciar sesión y renovar tokens.
    await backend.actualizarUsuarioAuth(id, { ban_duration: activo ? "none" : DURACION_BLOQUEO });
  } catch (error) {
    await backend.actualizarPerfil(id, { activo: perfil.activo }).catch((e) =>
      console.error("No se pudo revertir el estado del perfil", id, e)
    );
    throw error;
  }

  await backend.auditar({
    actor_id: actor.id,
    actor_email: actor.email,
    accion: activo ? "usuario.activar" : "usuario.desactivar",
    entidad: "usuario",
    entidad_id: id,
    detalle: { email: perfil.email },
  });
  return { ok: true, usuario_id: id };
}

async function restablecerPassword(
  backend: Backend,
  actor: Actor,
  cuerpo: Cuerpo,
): Promise<Resultado> {
  const id = validarUsuarioId(cuerpo.usuario_id);
  const password = validarPassword(cuerpo.password);
  const perfil = await perfilExistente(backend, id);

  await backend.actualizarUsuarioAuth(id, { password });
  await backend.auditar({
    actor_id: actor.id,
    actor_email: actor.email,
    accion: "usuario.restablecer_password",
    entidad: "usuario",
    entidad_id: id,
    detalle: { email: perfil.email },
  });
  return { ok: true, usuario_id: id };
}

// Punto de entrada -------------------------------------------------------------

export function crearManejador(backend: Backend): (req: Request) => Promise<Response> {
  return async (req) => {
    try {
      if (req.method !== "POST") {
        throw new ErrorHttp(405, "metodo_no_permitido", "Solo se acepta POST");
      }
      const actor = await autenticarAdmin(req, backend);

      let cuerpo: Cuerpo;
      try {
        cuerpo = await req.json();
      } catch {
        throw new ErrorHttp(400, "dato_invalido", "El cuerpo debe ser JSON");
      }
      if (typeof cuerpo !== "object" || cuerpo === null || Array.isArray(cuerpo)) {
        throw new ErrorHttp(400, "dato_invalido", "El cuerpo debe ser un objeto JSON");
      }

      switch (cuerpo.accion) {
        case "crear":
          return responder(201, await crear(backend, actor, cuerpo));
        case "cambiar_rol":
          return responder(200, await cambiarRol(backend, actor, cuerpo));
        case "cambiar_estado":
          return responder(200, await cambiarEstado(backend, actor, cuerpo));
        case "restablecer_password":
          return responder(200, await restablecerPassword(backend, actor, cuerpo));
        default:
          throw new ErrorHttp(400, "accion_desconocida", "Acción no reconocida");
      }
    } catch (error) {
      if (error instanceof ErrorHttp) {
        return responder(error.status, { error: error.message, codigo: error.codigo });
      }
      console.error("admin-usuarios: error no controlado", error);
      return responder(500, { error: "Error interno del servidor", codigo: "error_interno" });
    }
  };
}
