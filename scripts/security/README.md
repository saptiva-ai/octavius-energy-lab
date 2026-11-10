# Security Scripts

Scripts para auditorías de seguridad y verificaciones.

## Scripts Disponibles

### Auditorías
- **`security-audit.sh`** - Auditoría de seguridad completa
  ```bash
  ./scripts/security/security-audit.sh
  ```
- **`security-audit-focused.sh`** - Auditoría enfocada en áreas críticas
- **`security-audit-precise.sh`** - Análisis de seguridad preciso
- **`security-check.sh`** - Verificación rápida de seguridad

### Mantenimiento
- **`remove-audit-system.sh`** - Remover sistema de auditoría (si no se usa)

## Uso Común

```bash
# Auditoría completa (recomendado antes de deploy)
./scripts/security/security-audit.sh

# Verificación rápida
./scripts/security/security-check.sh
```

## ¿Qué verifican?

Las auditorías verifican:
- Secrets hardcoded en código
- Variables de entorno expuestas
- Configuraciones inseguras
- Dependencias con vulnerabilidades
- Permisos de archivos
- Configuración de Docker
- Certificados SSL/TLS

## Uso en CI/CD

```bash
# En pipeline de CI/CD
./scripts/security/security-check.sh || exit 1
```

---
**Ver también:** `../README.md` para más información
