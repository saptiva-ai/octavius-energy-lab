# Observability Configuration

This directory contains configuration files for the Copilotos Bridge observability stack.

## Configuration Files

- `prometheus.yml` - Prometheus scrape configuration
- `loki.yml` - Loki log storage configuration
- `promtail.yml` - Promtail log collection configuration
- `grafana/` - Grafana datasources and dashboards

## Documentation

**📚 Complete documentation is available at: [`docs/observability/`](../../docs/observability/)**

- [**Setup Guide**](../../docs/observability/setup.md) - Installation and configuration
- [**Metrics Reference**](../../docs/observability/metrics.md) - All available metrics
- [**Dashboards Guide**](../../docs/observability/dashboards.md) - Using Grafana
- [**Troubleshooting**](../../docs/observability/troubleshooting.md) - Common issues
- [**Production Guide**](../../docs/observability/production.md) - Deployment best practices
- [**Architecture**](../../docs/observability/architecture.md) - System design

## Quick Start

```bash
# Start monitoring stack
make obs-up

# Access Grafana
open http://localhost:3001
# Login: admin/admin

# Stop monitoring
make obs-down
```

See [docs/observability/README.md](../../docs/observability/README.md) for complete guide.
