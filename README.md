# Investigación de estrategias cuantitativas cripto

Proyecto de investigación reproducible para BTC/ETH spot. **Estado: experimental, sin operaciones reales y sin rentabilidad futura demostrada.** Los backtests son retrospectivos; sus resultados no constituyen una muestra ciega ni una promesa de rendimiento.

## Candidata congelada

`confirm3_vol0.3` combina una tendencia de 4 horas confirmada durante tres velas con un tamaño ajustado semanalmente por volatilidad. Usa dos carteras virtuales inicialmente iguales para BTC y ETH; no redistribuye entre ellas y no usa shorts ni apalancamiento. La regla exacta está en [ITERACION_RESULTADO.md](ITERACION_RESULTADO.md) y sus parámetros en [candidate_frozen.json](iteration_03_results/candidate_frozen.json).

La investigación original mostró resultados históricos positivos, sensibles a costos y selección. El intervalo de comparación con una referencia sencilla incluye cero. No interpretar los datos históricos como un resultado esperado.

## Instalación y comprobación

Requiere Python 3.10 o superior. Desde esta carpeta:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python replay_reference.py --start 2023-01-01 --end 2026-11-06
```

Las pruebas contrastan la señal nueva contra la investigación congelada, verifican que el futuro no altere señales previas y comprueban contabilidad y paridad con el motor auditado. Utilizan los CSV históricos incluidos. Los scripts históricos de descarga acceden a Binance; revise su código antes de ejecutarlos.

## Componentes

- `quantbot/strategy.py`: señal congelada, sin red ni órdenes.
- `quantbot/ledger.py`: replay spot con efectivo, unidades y registro de transacciones; no envía órdenes.
- `quantbot/data.py` y `replay_reference.py`: validación OHLCV y replay local por activo. El final del período es exclusivo; el valor final es marcado a mercado y no incluye una venta hipotética de cierre. Los CSV de salida se escriben en `replay_output/`.
- `tests/`: comprobaciones del comportamiento de referencia.
- `audit_backtests.py` y `audit_*.csv`: motor independiente y resultados de auditoría.
- `iteration_02.py`, `iteration_03.py`, `iteration_03_portfolio.py`: hipótesis y resultados de las iteraciones.
- `*_spot_4h.csv`, otros CSV y carpetas `iteration_*_results`: datos y resultados históricos para reproducir la investigación.
- [PLAN_MEJORA_BOT.md](PLAN_MEJORA_BOT.md): hoja de ruta, incluyendo paper trading, ejecución y controles pendientes.
- [PROGRESO.md](PROGRESO.md): pasos completados y pendientes de implementación.
- [REVISION_AUDITORIA.md](REVISION_AUDITORIA.md): errores detectados y limitaciones de las pruebas previas.
- [INFORME_BACKTEST.md](INFORME_BACKTEST.md): registro de intentos anteriores; contiene resultados provisionales y debe leerse junto a la auditoría.

## Estado y siguientes pasos

Se separaron la señal y el ledger del código de exploración y se agregaron comprobaciones de paridad y contabilidad. Faltan persistencia y reinicio, ledger completo de cada backtest, validación de datos en producción, costos observados, reconciliación y modo sombra. No hay adaptador de órdenes reales ni credenciales en el proyecto. Antes de evaluar cualquier despliegue, completar las puertas de avance del plan.

Los datos tienen un hueco de cuatro horas en febrero de 2020. Las marcas y costos usados en simulación no representan necesariamente precios ejecutables. Los archivos de investigación anteriores se conservan para trazabilidad, no como estrategias listas para operar.
