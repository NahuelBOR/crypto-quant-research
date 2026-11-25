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

## Rebalanceo mensual del S&P 500

La cartera mantiene un objetivo de 75% en SPY y reparte el otro 25% por igual entre los nueve ETF sectoriales originales (XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV y XLY). En la primera apertura de cada mes vuelve a esos pesos. Durante el mes deja que varíen. Esta asignación reduce el peso relativo de los sectores más grandes y aumenta el de los más chicos. Los sectores de comunicación e inmobiliario incorporados posteriormente quedan representados a través de SPY.

| Cartera | Feb. 2000–13 nov. 2026, anualizado | Desde 2016, anualizado | Caída máxima del período completo |
|---|---:|---:|---:|
| 75% SPY + 25% sectores, rebalanceo mensual | 8,60% | 14,32% | −54,77% |
| Misma compra inicial, mantenida sin rebalancear | 8,39% | 13,88% | −54,31% |
| SPY | 8,38% | 14,61% | −55,19% |
| Rotación hacia los sectores con mejor rendimiento relativo a 6 y 12 meses | 8,30% | 13,63% | −52,20% |
| Reducir SPY al 50% cuando caen el índice y la mayoría de los sectores | 7,56% | 12,23% | −43,10% |

Se usan aperturas y cierres ajustados de Yahoo Finance como aproximación a los dividendos reinvertidos. Cada compra y venta cuesta 0,05% del importe operado, incluida la liquidación final. Se permiten fracciones de participación. El efectivo rinde cero y se omiten impuestos. Las carteras continúan entre subperíodos. Los ETF sectoriales cambian de composición a lo largo de la muestra.

La estrategia de pesos iguales surgió como control de la rotación. Superó a SPY en 14 de 25 años completos. La ventaja anualizada total fue de 0,22 puntos y cayó a 0,19 puntos al subir el costo por lado a 0,30%. El intervalo del 95% para el crecimiento anual relativo fue de −0,22% a +0,62% (5.000 remuestreos pareados en bloques de seis meses completos, sin corrección por selección). La ventaja reciente cambió de signo. En una comparación anterior con datos de Kenneth French, la misma proporción entre el mercado estadounidense y doce industrias obtuvo 10,81% anual frente a 10,62% del mercado en 1927–1997. Son carteras académicas y se omiten los costos internos de replicarlas.

```powershell
python research/sector_rotation.py
python research/sector_industry_history.py
python research/sector_rotation.py --signal 2026-11-02 --rule equal_sectors
```

El último comando muestra los pesos de la sesión indicada para simulación. Las series de resultados se guardan en `research/sector_rotation_results/`. La primera ejecución descarga los precios y los archivos de industrias. Las siguientes reutilizan la copia en `replay_output/sector_prices/`. [ETF sectoriales de State Street](https://www.ssga.com/us/en/intermediary/capabilities/equities/sector-investing/select-sector-etfs) · [Datos de Kenneth French](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html)

## Prueba de 2020–2021

La regla original dio +271,8% acumulado (+141,7% en 2020 y +53,8% en 2021), con una caída máxima diaria de 12,4%. Con el doble de costos y una demora adicional de cuatro horas, el retorno acumulado fue +254,0%. Mantener BTC y ETH rindió +1.639,1%, con una caída máxima de 58,8%. La cartera con 25% en cripto y 75% en efectivo rindió +130,9%, con una caída máxima de 17,1%.

Se usan velas spot de Binance de cuatro horas, historial anterior para inicializar indicadores y 0,15% de costo base por lado. Las dos cuentas parten 50/50, continúan entre los años y no se rebalancean entre sí. Falta una vela por activo el 19 de febrero de 2020, sin relleno de precios. Ambos años ya formaron parte de la muestra de selección, por lo que esta corrida es descriptiva.

```powershell
python research/backtest_2020_2021.py
```

## Alcance

Los backtests son retrospectivos y no demuestran rentabilidad futura. Los costos y precios de ejecución son supuestos; el historial de BTC y ETH tiene un hueco de cuatro horas en febrero de 2020. Quedan pendientes el estado persistente, la reconciliación, el paper trading en tiempo real y la medición de costos observados. No hay credenciales ni adaptador de órdenes reales en este proyecto.
