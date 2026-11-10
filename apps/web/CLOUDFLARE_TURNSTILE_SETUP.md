# Cloudflare Turnstile Setup

## ¿Qué es Turnstile?

Cloudflare Turnstile es un CAPTCHA invisible que valida que los usuarios son humanos sin interrumpir su experiencia. Ayuda a que Cloudflare confíe en las peticiones y no muestre challenges invasivos.

## Propósito

Soluciona el error 403 al subir archivos en producción cuando Cloudflare está configurado con reglas de seguridad estrictas, **sin necesidad de deshabilitar protecciones OWASP**.

## Configuración (5 minutos)

### Paso 1: Obtener Site Key y Secret Key

1. Ve a **Cloudflare Dashboard**: https://dash.cloudflare.com
2. Selecciona tu dominio: `saptiva.com`
3. Navega: **Turnstile** (en el menú lateral)
4. Click: **Add site**
5. Configura:
   ```
   Site name: OctaviOS File Uploads
   Domain:    retail.saptiva.com
   Widget mode: Invisible
   ```
6. Click **Create**
7. Copia:
   - **Site Key** (público - se usa en frontend)
   - **Secret Key** (privado - se usa en backend)

### Paso 2: Configurar Variables de Entorno

**Frontend** (`apps/web/.env.local`):

```bash
# Cloudflare Turnstile (público - se puede exponer)
NEXT_PUBLIC_TURNSTILE_SITE_KEY=0x4AAA...tu-site-key
```

**Backend** (`apps/backend/.env` o `envs/.env.prod`):

```bash
# Cloudflare Turnstile Secret (privado - NO commitear)
CLOUDFLARE_TURNSTILE_SECRET_KEY=0x4AAA...tu-secret-key
```

### Paso 3: Reiniciar Servicios

**Desarrollo**:

```bash
# Frontend
cd apps/web
npm run dev

# Backend (si vas a validar el token)
cd apps/backend
python -m uvicorn src.main:app --reload
```

**Producción**:

```bash
# Rebuild y redeploy
docker-compose build web
docker-compose up -d web
```

## Cómo Funciona

### 1. Usuario Inicia Upload

```typescript
// FileUploadButton.tsx
const { execute: executeTurnstile } = useTurnstile(siteKey);
const turnstileToken = await executeTurnstile();
```

### 2. Token se Envía con Upload

```typescript
// useFiles.ts
formData.append("cf-turnstile-response", turnstileToken);
await fetch("/api/files/upload", { body: formData });
```

### 3. Cloudflare Valida Token

```
Browser → [Cloudflare ve token Turnstile] → ✅ Confía y permite → Next.js → Backend
```

## Verificación

### Test 1: Verificar que Site Key está cargada

```bash
# En DevTools Console de https://retail.saptiva.com
console.log(process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY);
// Debe mostrar: "0x4AAA..."
```

### Test 2: Verificar que Turnstile se carga

```bash
# En DevTools Console
console.log(window.turnstile);
// Debe mostrar: {render: ƒ, execute: ƒ, reset: ƒ, ...}
```

### Test 3: Subir Archivo

1. Abre https://retail.saptiva.com
2. Intenta subir un archivo
3. En **DevTools → Network**, busca la petición a `/api/files/upload`
4. Verifica que el FormData incluye `cf-turnstile-response`

## Seguridad

### ¿Es seguro?

✅ **Sí** - Turnstile NO deshabilita seguridad:

- Todas las protecciones OWASP siguen activas
- Solo ayuda a Cloudflare a identificar usuarios legítimos
- El token es de un solo uso (no reutilizable)
- Expira después de 5 minutos

### ¿Qué pasa si no está configurado?

- El sistema funciona igual
- Fallback automático a **Challenge-Redirect Flow**
- El usuario verá un challenge de Cloudflare y podrá resolverlo

## Troubleshooting

### Error: "Turnstile not ready yet"

**Causa**: Script de Turnstile no cargó
**Solución**: Verifica conexión a internet y que no haya bloqueadores de ads

### Error: "Turnstile verification failed"

**Causa**: Site key incorrecta o dominio no coincide
**Solución**: Verifica que la site key sea correcta y el dominio esté registrado

### Upload aún falla con 403

**Causa**: Cloudflare no reconoce el token
**Solución**:

1. Verifica que el site key sea para `retail.saptiva.com`
2. Verifica que el dominio en Turnstile settings coincida
3. Revisa Cloudflare Logs: Security → Overview → Activity log

## Referencias

- [Cloudflare Turnstile Docs](https://developers.cloudflare.com/turnstile/)
- [Turnstile Widget Modes](https://developers.cloudflare.com/turnstile/get-started/)
- [Frontend Implementation](../../src/hooks/useTurnstile.ts)
- [Integration in FileUploadButton](../../src/components/files/FileUploadButton.tsx)

---

**Última actualización**: 2025-12-17
**Versión**: 1.2.4
