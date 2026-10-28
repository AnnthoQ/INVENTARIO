-- =============================================================================
-- Capa 2 · Paso 1 de 2: rol «trabajador»
--
-- Va en una migración aparte porque PostgreSQL no permite usar un valor nuevo
-- de un enum dentro de la misma transacción en la que se crea.
-- =============================================================================

alter type public.user_role add value if not exists 'trabajador';
