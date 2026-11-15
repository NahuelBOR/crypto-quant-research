# Crypto Quant Research

Investigación de estrategias sistemáticas para BTC y ETH spot, con datos históricos, pruebas y herramientas para reproducir los resultados.

## Estrategia de referencia

La estrategia `confirm3_vol0.3` utiliza velas de cuatro horas. La condición de tendencia es EMA20 > EMA100 y cierre > SMA200; se confirma durante tres velas consecutivas para entrar o salir. El tamaño se ajusta semanalmente según la volatilidad reciente, con exposición objetivo máxima del 100% y efectivo cuando la señal está apagada.

La simulación mantiene carteras independientes de BTC y ETH, con un reparto inicial 50/50. Es una estrategia de investigación: no utiliza apalancamiento ni envía órdenes reales.

## Instalación

Requiere Python 3.10 o superior. En PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Uso

Ejecutar las pruebas:

```powershell
python -m unittest discover -s tests -v
```

Reproducir las señales y transacciones simuladas para BTC y ETH:

```powershell
python replay_reference.py --start 2023-01-01 --end 2026-11-06
```

El final del período es exclusivo. Los archivos de operaciones y saldos se guardan en `replay_output/`. El equity final está marcado a mercado y no incluye una venta hipotética de cierre.

## Estructura

```text
quantbot/              Señales, validación de datos y contabilidad spot
tests/                 Pruebas de referencia y contabilidad
research/              Datos históricos, experimentos y resultados
replay_reference.py    Replay local de la estrategia de referencia
requirements.txt       Dependencias
```

En `research/iteration_03_results/` están los parámetros y resultados de la estrategia de referencia. El resto de `research/` conserva pruebas históricas, incluidas variantes descartadas y motores anteriores con limitaciones conocidas. Algunos scripts de descarga acceden a Binance y pueden sobrescribir datos; revisar sus instrucciones antes de ejecutarlos.

La prueba de 2022 está en `research/backtest_2022_results/`. Para volver a descargar las velas de 2021–2022 y recalcularla: `python research/backtest_2022.py`. El año 2021 se usa para inicializar indicadores; 2022 ya participó en la selección de la estrategia y no es una muestra independiente.

También está disponible la prueba de 2018–2019 en `research/backtest_2018_2019_results/`; se ejecuta con `python research/backtest_2018_2019.py` y descarga datos desde agosto de 2017 para inicializar indicadores. Con costos supuestos de 0,15% por lado, la cartera obtuvo un 26,5% acumulado (−13,5% en 2018 y +46,2% en 2019). Hay 15 velas faltantes por activo; los indicadores cuentan velas disponibles y la ejecución pasa a la apertura disponible siguiente. Este período también se examinó con otras reglas durante la investigación, por lo que no es completamente ciego.

Para SPY se probó una adaptación a sesiones diarias, no una réplica exacta de las velas cripto: EMA3/12, SMA24, una sesión de confirmación y volatilidad de 21 sesiones. `python research/backtest_spy.py` descarga datos de Yahoo Finance y produce `research/backtest_spy_results/`. En 1994–13 de noviembre de 2026 la adaptación obtuvo 2,9% CAGR con costo supuesto de 0,05% por lado; SPY pasivo obtuvo 10,8% y una referencia mitad SPY/mitad efectivo 5,7%, bajo el mismo supuesto de costo. El efectivo rinde cero, y los precios ajustados son una aproximación de dividendos reinvertidos, no precios históricos ejecutables.

En la simulación de 2022, la cartera de referencia perdió 7,8% y tuvo una caída máxima diaria de 12,7%, con un costo supuesto de 15 pb por operación. Una referencia pasiva calibrada con la volatilidad de 2021 perdió 19,9% y tuvo una caída máxima de 22,9%. Son resultados históricos sujetos a las limitaciones del modelo, no una prueba de ausencia de sobreajuste.

## Alcance

Los backtests son retrospectivos y no demuestran rentabilidad futura. Los costos y precios de ejecución son supuestos; el historial de BTC y ETH tiene un hueco de cuatro horas en febrero de 2020. Quedan pendientes el estado persistente, la reconciliación, el paper trading en tiempo real y la medición de costos observados. No hay credenciales ni adaptador de órdenes reales en este proyecto.
