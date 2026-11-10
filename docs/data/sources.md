# Fuentes de datos y modelos

Fecha de consulta: 2026-11-10. **[V]** = verificado ese día con la página o con una consulta real. **[NV]** = no verificado.

## Principal: CENACE (México)

### Precios: servicios web SW-PML y SW-PEND [V]

- **PML por nodo:**
  - URL: `https://ws01.cenace.gob.mx:8082/SWPML/SIM/{SIN|BCA|BCS}/{MDA|MTR}/{nodos}/{AAAA/MM/DD}/{AAAA/MM/DD}/JSON`.
  - Campos: `fecha`, `hora` (1-24), `pml`, `pml_ene`, `pml_per` y `pml_cng`. Los números llegan como texto.
- **Precio por zona de carga:**
  - URL: `.../SWPEND/SIM/{sistema}/{proceso}/{zonas}/...`.
  - Campos: `zona_carga`, `pz`, `pz_ene`, `pz_per` y `pz_cng`.
- **Límites que impone el servicio:**
  - Máximo 7 días por consulta.
  - Máximo 20 nodos o zonas por consulta.
  - Una clave inexistente devuelve `ZERO_RESULTS` en lugar de un error.
- **Histórico:** febrero de 2017 en MTR devuelve datos, mientras que 2016 responde "Las fechas son menores al inicio del mercado".
- **Volumen estimado [NV]:** suponiendo unos 2,400 nodos, 2018 a 2025 daría unos 168 millones de filas por proceso y unos 337 millones con MDA y MTR. Son 25 a 35 GB en Postgres y unas 50,000 llamadas por proceso.
- **Notas para el diseño:**
  - `hora` va de 1 a 24, en hora local. Hay que definir la conversión a `timestamptz` y el manejo del horario de verano, que se abolió en 2022.
  - Los PML pueden ser negativos o cero [NV], lo que confirma que no se debe usar MAPE.

### Demanda horaria del Sistema Eléctrico Nacional [V parcial]

- **Página:** https://www.cenace.gob.mx/Paginas/SIM/Reportes/EstimacionDemandaReal.aspx
  - Trae la demanda real "Por Balance" y "Por Retiros".
  - Se consulta por rango de fechas y se descarga en CSV, PDF o HTML.
  - Es un portal ASP.NET **sin API documentada**.
- **[NV]:**
  - El desglose por gerencia regional y por sistema.
  - Desde qué año hay histórico.
  - Si se publica el pronóstico de demanda que permitiría usarlo como baseline.
  - Se verifica en el PR de ingesta de CENACE antes de escribir el conector.

### Licencia [NV]

- No hay términos de uso explícitos en las páginas de CENACE.
- El servicio marca los datos como `area: "PÚBLICA"`, que no equivale a una licencia.
- Libre Uso MX aplicaría si los conjuntos estuvieran en datos.gob.mx, pero ese portal respondió 403.
- **Decisión:** el repositorio **no redistribuye** datos crudos de CENACE. Publica los conectores; cada usuario descarga los datos, y los agregados o resultados citan la fuente.

## Secundario: Low Carbon London [V]

- **Dataset:** https://data.london.gov.uk/dataset/smartmeter-energy-consumption-data-in-london-households-vqm0d. Licencia CC BY 4.0.
  - 5,567 hogares, lecturas cada 30 minutos, de noviembre de 2011 a febrero de 2014, unos 167 millones de filas.
- **Archivos:**
  - `LCL-FullData.zip` (764.54 MB).
  - `Partitioned LCL Data.zip` (168 CSV, 758.86 MB, con el encabezado repetido en cada archivo).
  - `Tariffs.xlsx`, con los precios dToU de 2013: High 67.20, Normal 11.76 y Low 3.99 p/kWh. La tarifa plana Std es de 14.228 p/kWh.
- **Pendientes:**
  - Los nombres de columna se confirman leyendo el encabezado del CSV.
  - El sitio no publica checksums; calculamos un sha256 propio.
- **Excluido:** el clima Dark Sky de la versión de Kaggle, porque su licencia de redistribución no está clara.

## Desarrollo: UCI ElectricityLoadDiagrams20112014 [V]

- 370 clientes, lecturas cada 15 minutos en kW, 140,256 filas en formato ancho.
- CC BY 4.0. El archivo descomprimido pesa 678 MB.

## Clima

| Fuente | Qué | Licencia | Uso |
|---|---|---|---|
| Open-Meteo Historical Forecast API [V] | Pronósticos archivados por hora desde ~2022, modelos GFS, ICON e IFS | Datos CC BY 4.0. API gratuita solo para uso no comercial (educativo cuenta), con menos de 10,000 llamadas al día | Covariable "pronóstico conocido al corte", que evita el leakage |
| SMN/CONAGUA, climatología diaria [V parcial] | Temperaturas máxima y mínima y precipitación diarias, más de 5,000 estaciones | "Términos y Condiciones SMN" [NV] | Observaciones; solo se usan como verdad pasada |

Un uso comercial de Saptiva AI requeriría el plan de pago de Open-Meteo o autoalojarlo.

## Festivos de México

Ley Federal del Trabajo, art. 74 (https://www.diputados.gob.mx/LeyesBiblio/pdf/LFT.pdf).

- **[V]:** fracciones I a III.
- **[NV]:** el resto. Se codifica como reglas y se valida contra el texto completo.

## Modelos

| Modelo | Licencia | Rol |
|---|---|---|
| Qwen3-8B | Apache-2.0 [V] | LLM del agente. Ollama `qwen3:8b` en Q4_K_M, 5.2 GB [V] |
| TimesFM 2.5 (200M) | Apache-2.0 en código y pesos [V] | Forecasting por defecto |
| TimesFM 3.0 | Pesos `timesfm-non-commercial-license-v1.0` [V] | Opt-in aislado, sin mirror de pesos |
| NVIDIA Auto Ontology | Apache-2.0 [V]. No acepta contribuciones externas | Capa semántica opt-in mediante su MCP |

**Pendiente:** confirmar qué versión del paquete pip `timesfm` expone la API de 2.5, porque el model card y el README se contradicen.
