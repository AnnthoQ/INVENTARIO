// Edge Function «admin-usuarios»: alta de usuarios, cambio de rol, activación
// y restablecimiento de contraseñas. Solo para administradores activos.
//
// Usa la service_role key que Supabase inyecta en el entorno de la función;
// esa clave nunca debe llegar a la aplicación de escritorio.

import { createClient, type SupabaseClient } from "npm:@supabase/supabase-js@2.45.4";
import { type Backend, crearManejador, ErrorHttp } from "./manejador.ts";

interface ErrorSupabase {
  message: string;
  status?: number;
  code?: string;
}

function errorDeAuth(error: ErrorSupabase): Error {
  if (error.code === "email_exists" || (error.status === 422 && /already/i.test(error.message))) {
    return new ErrorHttp(409, "email_existente", "Ya existe un usuario con ese correo o código");
  }
  if (error.code === "weak_password") {
    return new ErrorHttp(400, "password_debil", "La contraseña no cumple la política de Supabase Auth");
  }
  return new Error(`Auth: ${error.message}`);
}

function errorDePerfil(error: ErrorSupabase): Error {
  // Mensaje del trigger proteger_ultimo_admin.
  if (error.message.includes("al menos un administrador")) {
    return new ErrorHttp(409, "ultimo_admin", "Debe quedar al menos un administrador activo");
  }
  return new Error(`profiles: ${error.message}`);
}

export function backendSupabase(cliente: SupabaseClient): Backend {
  const ahora = () => new Date().toISOString();

  return {
    async usuarioDelToken(jwt) {
      const { data, error } = await cliente.auth.getUser(jwt);
      if (error || !data.user) return null;
      return { id: data.user.id, email: data.user.email ?? null };
    },

    async perfil(id) {
      const { data, error } = await cliente
        .from("profiles")
        .select("role, activo, email")
        .eq("id", id)
        .maybeSingle();
      if (error) throw errorDePerfil(error);
      return data;
    },

    async crearUsuarioAuth(email, password, nombre) {
      const { data, error } = await cliente.auth.admin.createUser({
        email,
        password,
        email_confirm: true,
        user_metadata: { full_name: nombre },
      });
      if (error) throw errorDeAuth(error);
      return data.user.id;
    },

    async eliminarUsuarioAuth(id) {
      const { error } = await cliente.auth.admin.deleteUser(id);
      if (error) throw errorDeAuth(error);
    },

    async crearPerfil(id, campos) {
      // handle_new_user ya insertó el perfil con el rol por defecto.
      const { error } = await cliente
        .from("profiles")
        .upsert({ id, ...campos, updated_at: ahora() });
      if (error) throw errorDePerfil(error);
    },

    async actualizarPerfil(id, campos) {
      const { error } = await cliente
        .from("profiles")
        .update({ ...campos, updated_at: ahora() })
        .eq("id", id);
      if (error) throw errorDePerfil(error);
    },

    async actualizarUsuarioAuth(id, atributos) {
      const { error } = await cliente.auth.admin.updateUserById(id, atributos);
      if (error) throw errorDeAuth(error);
    },

    async auditar(entrada) {
      const { error } = await cliente.from("auditoria").insert(entrada);
      // El cambio ya se aplicó: un fallo de auditoría se registra pero no se revierte.
      if (error) console.error("No se pudo registrar la auditoría", entrada.accion, error.message);
    },
  };
}

const url = Deno.env.get("SUPABASE_URL");
const claveServicio = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
if (!url || !claveServicio) {
  throw new Error("Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY en el entorno de la función");
}

const cliente = createClient(url, claveServicio, {
  auth: { persistSession: false, autoRefreshToken: false },
});

Deno.serve(crearManejador(backendSupabase(cliente)));
