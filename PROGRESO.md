# Progreso de implementación

## Primera entrega

- Candidata y resultados históricos conservados, con auditoría de los errores anteriores.
- Señal congelada extraída a `quantbot/strategy.py` y verificada contra la investigación previa.
- Replay spot separado en `quantbot/ledger.py`: efectivo, unidades, costos y registro por operación.
- Comprobaciones básicas de integridad OHLCV; los huecos se reportan, no se inventan precios.
- Replay local de BTC/ETH con salida de operaciones y marcas en `replay_output/`.
- Siete pruebas: paridad de señal y equity, ausencia de uso de futuro, contabilidad, costos, inicio del período y validación básica de datos.
- README, plan y datos históricos versionados; no hay ejecución de órdenes reales.

## Pendiente

- Estado persistente, reinicio y deduplicación de velas/órdenes.
- Registro de la causa de cada decisión, fills simulados parciales y reconciliación.
- Análisis detallado por operación, métricas intradía y benchmarks integrados en el replay.
- Captación continua de datos y paper trading en tiempo real.
- Costos observados, validación temporal nueva, controles operativos y documentación de resultados prospectivos.

Este es el primer incremento del plan, no su finalización. El rendimiento pasado de la candidata no constituye evidencia de rentabilidad futura.
