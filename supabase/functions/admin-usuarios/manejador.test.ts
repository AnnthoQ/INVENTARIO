// deno test supabase/functions/admin-usuarios/
import { assert, assertEquals, assertFalse } from "jsr:@std/assert@1.0.13";
import {
  type Actor,
  type Backend,
  crearManejador,
  DURACION_BLOQUEO,
  type EntradaAuditoria,
  ErrorHttp,
  type Perfil,
} from "./manejador.ts";

const ADMIN = "00000000-0000-0000-0000-0000000000a1";
const TRABAJADOR = "00000000-0000-0000-0000-0000000000b1";

class BackendFalso implements Backend {
  perfiles = new Map<string, Perfil>([
    [ADMIN, { role: "admin", activo: true, email: "admin@example.com" }],
    [TRABAJADOR, { role: "trabajador", activo: true, email: "op@inv.local" }],
  ]);
  tokens = new Map<string, Actor>([
    ["token-admin", { id: ADMIN, email: "admin@example.com" }],
    ["token-trabajador", { id: TRABAJADOR, email: "op@inv.local" }],
  ]);
  auth = new Map<string, { email: string; password?: string; ban_duration?: string }>();
  auditoria: EntradaAuditoria[] = [];
  falloAlCrearPerfil = false;
  falloAlBloquear = false;
  private siguiente = 1;

  usuarioDelToken(jwt: string) {
    return Promise.resolve(this.tokens.get(jwt) ?? null);
  }
  perfil(id: string) {
    return Promise.resolve(this.perfiles.get(id) ?? null);
  }
  crearUsuarioAuth(email: string, password: string) {
    const id = `00000000-0000-0000-0000-${String(this.siguiente++).padStart(12, "0")}`;
    this.auth.set(id, { email, password });
    return Promise.resolve(id);
  }
  eliminarUsuarioAuth(id: string) {
    this.auth.delete(id);
    return Promise.resolve();
  }
  crearPerfil(id: string, campos: Record<string, unknown>) {
    if (this.falloAlCrearPerfil) return Promise.reject(new Error("fallo simulado"));
    this.perfiles.set(id, campos as unknown as Perfil);
    return Promise.resolve();
  }
  actualizarPerfil(id: string, campos: Record<string, unknown>) {
    this.perfiles.set(id, { ...this.perfiles.get(id)!, ...campos });
    return Promise.resolve();
  }
  actualizarUsuarioAuth(id: string, atributos: { password?: string; ban_duration?: string }) {
    if (this.falloAlBloquear && atributos.ban_duration) {
      return Promise.reject(new Error("fallo simulado"));
    }
    this.auth.set(id, { ...this.auth.get(id)!, ...atributos });
    return Promise.resolve();
  }
  auditar(entrada: EntradaAuditoria) {
    this.auditoria.push(entrada);
    return Promise.resolve();
  }
}

function solicitud(cuerpo: unknown, token: string | null = "token-admin"): Request {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  return new Request("http://localhost/admin-usuarios", {
    method: "POST",
    headers,
    body: typeof cuerpo === "string" ? cuerpo : JSON.stringify(cuerpo),
  });
}

async function invocar(backend: Backend, req: Request) {
  const respuesta = await crearManejador(backend)(req);
  return { status: respuesta.status, cuerpo: await respuesta.json() };
}

const ALTA = {
  accion: "crear",
  email: "Nuevo@Inv.Local",
  password: "clave2026",
  nombre: "Nuevo Trabajador",
  rol: "trabajador",
};

Deno.test("sin token responde 401", async () => {
  const { status } = await invocar(new BackendFalso(), solicitud(ALTA, null));
  assertEquals(status, 401);
});

Deno.test("un trabajador no puede gestionar usuarios", async () => {
  const backend = new BackendFalso();
  const { status, cuerpo } = await invocar(backend, solicitud(ALTA, "token-trabajador"));
  assertEquals(status, 403);
  assertEquals(cuerpo.codigo, "no_autorizado");
  assertEquals(backend.auth.size, 0);
});

Deno.test("un administrador desactivado no puede gestionar usuarios", async () => {
  const backend = new BackendFalso();
  backend.perfiles.get(ADMIN)!.activo = false;
  const { status } = await invocar(backend, solicitud(ALTA));
  assertEquals(status, 403);
});

Deno.test("crear: alta en Auth, perfil con rol y auditoría sin contraseña", async () => {
  const backend = new BackendFalso();
  const { status, cuerpo } = await invocar(backend, solicitud(ALTA));
  assertEquals(status, 201);
  const perfil = backend.perfiles.get(cuerpo.usuario_id)!;
  assertEquals(perfil.role, "trabajador");
  assertEquals(perfil.email, "nuevo@inv.local");
  assertEquals(backend.auditoria[0].accion, "usuario.crear");
  assertEquals(backend.auditoria[0].actor_id, ADMIN);
  assertFalse(JSON.stringify(backend.auditoria).includes("clave2026"));
});

Deno.test("crear: rechaza contraseñas débiles antes de tocar Auth", async () => {
  const backend = new BackendFalso();
  const { status, cuerpo } = await invocar(backend, solicitud({ ...ALTA, password: "solotexto" }));
  assertEquals(status, 400);
  assertEquals(cuerpo.codigo, "password_debil");
  assertEquals(backend.auth.size, 0);
});

Deno.test("crear: rechaza roles no asignables", async () => {
  const { status } = await invocar(new BackendFalso(), solicitud({ ...ALTA, rol: "host" }));
  assertEquals(status, 400);
});

Deno.test("crear: si falla el perfil se deshace el alta en Auth", async () => {
  const backend = new BackendFalso();
  backend.falloAlCrearPerfil = true;
  const { status } = await invocar(backend, solicitud(ALTA));
  assertEquals(status, 500);
  assertEquals(backend.auth.size, 0);
  assertEquals(backend.auditoria.length, 0);
});

Deno.test("cambiar_rol: no sobre la propia cuenta", async () => {
  const { status, cuerpo } = await invocar(
    new BackendFalso(),
    solicitud({ accion: "cambiar_rol", usuario_id: ADMIN, rol: "trabajador" }),
  );
  assertEquals(status, 409);
  assertEquals(cuerpo.codigo, "propio_usuario");
});

Deno.test("cambiar_rol: actualiza y audita el rol anterior", async () => {
  const backend = new BackendFalso();
  const { status } = await invocar(
    backend,
    solicitud({ accion: "cambiar_rol", usuario_id: TRABAJADOR, rol: "admin" }),
  );
  assertEquals(status, 200);
  assertEquals(backend.perfiles.get(TRABAJADOR)!.role, "admin");
  assertEquals(backend.auditoria[0].detalle, {
    email: "op@inv.local",
    rol_anterior: "trabajador",
    rol_nuevo: "admin",
  });
});

Deno.test("cambiar_rol: propaga el error del último administrador", async () => {
  const backend = new BackendFalso();
  backend.actualizarPerfil = () =>
    Promise.reject(new ErrorHttp(409, "ultimo_admin", "Debe quedar al menos un administrador activo"));
  const { status, cuerpo } = await invocar(
    backend,
    solicitud({ accion: "cambiar_rol", usuario_id: TRABAJADOR, rol: "admin" }),
  );
  assertEquals(status, 409);
  assertEquals(cuerpo.codigo, "ultimo_admin");
});

Deno.test("cambiar_estado: desactivar bloquea en Auth y en el perfil", async () => {
  const backend = new BackendFalso();
  const { status } = await invocar(
    backend,
    solicitud({ accion: "cambiar_estado", usuario_id: TRABAJADOR, activo: false }),
  );
  assertEquals(status, 200);
  assertFalse(backend.perfiles.get(TRABAJADOR)!.activo);
  assertEquals(backend.auth.get(TRABAJADOR)!.ban_duration, DURACION_BLOQUEO);
  assertEquals(backend.auditoria[0].accion, "usuario.desactivar");
});

Deno.test("cambiar_estado: si falla el bloqueo se revierte el perfil", async () => {
  const backend = new BackendFalso();
  backend.falloAlBloquear = true;
  const { status } = await invocar(
    backend,
    solicitud({ accion: "cambiar_estado", usuario_id: TRABAJADOR, activo: false }),
  );
  assertEquals(status, 500);
  assert(backend.perfiles.get(TRABAJADOR)!.activo);
});

Deno.test("cambiar_estado: exige un booleano", async () => {
  const { status } = await invocar(
    new BackendFalso(),
    solicitud({ accion: "cambiar_estado", usuario_id: TRABAJADOR, activo: "no" }),
  );
  assertEquals(status, 400);
});

Deno.test("restablecer_password: cambia la clave y no la audita", async () => {
  const backend = new BackendFalso();
  const { status } = await invocar(
    backend,
    solicitud({ accion: "restablecer_password", usuario_id: TRABAJADOR, password: "nueva2026x" }),
  );
  assertEquals(status, 200);
  assertEquals(backend.auth.get(TRABAJADOR)!.password, "nueva2026x");
  assertFalse(JSON.stringify(backend.auditoria).includes("nueva2026x"));
});

Deno.test("restablecer_password: 404 si el usuario no existe", async () => {
  const { status } = await invocar(
    new BackendFalso(),
    solicitud({
      accion: "restablecer_password",
      usuario_id: "00000000-0000-0000-0000-0000000000ff",
      password: "nueva2026x",
    }),
  );
  assertEquals(status, 404);
});

Deno.test("acción desconocida y cuerpo inválido responden 400", async () => {
  const backend = new BackendFalso();
  assertEquals((await invocar(backend, solicitud({ accion: "borrar_todo" }))).status, 400);
  assertEquals((await invocar(backend, solicitud("no es json"))).status, 400);
});
