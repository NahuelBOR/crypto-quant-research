# Revisión de los backtests — 06-11-2026

**Sí hay una candidata rentable históricamente; no hay todavía una estrategia ganadora demostrada para operar en vivo.** Retiro la recomendación anterior de la mezcla 60/40 basada en el 13% anual: necesita reconstrucción contable antes de poder usarse como evidencia. Esta revisión tiene prioridad sobre las conclusiones anteriores.

## Qué encontré

- `ensemble_quant_backtest.py`: el momentum semanal inicializa todos los días con cero; `ffill()` no propaga los lunes. En realidad abre durante un intervalo y cierra. Lo reproduje con una comprobación del código original. Afecta sus comparaciones y la conclusión de descartar ese sleeve; no explica por sí solo el resultado final 60/40, que ya no lo incluía.
- Los motores de pesos calculan costos por cambios del peso objetivo, pero omiten operaciones necesarias para recomponer esos pesos cuando los precios cambian. Un peso constante no implica cero operaciones. También hay mezclas/reselecciones de series precalculadas sin contabilizar todos los cambios de capital entre sleeves.
- El carry aproximado usa diferencias de retornos porcentuales y división por dos. Eso no mantiene necesariamente las mismas unidades spot y perpetuo ni modela saldos de efectivo/colateral. Sus Sharpes altos no justifican confianza sin reconciliar cantidades, timestamps de funding y costos de cada operación.
- En `expanded_backtest.py`, el bootstrap dice comparar 2023+ pero recibe las series completas devueltas por `score`: incluye años anteriores. No afecta automáticamente todas las otras pruebas bootstrap, pero invalida esa interpretación concreta.
- Cambiamos universo, sleeves y pesos después de observar 2023–2026. Elegir luego un peso usando 2020–2022 no convierte todo el diseño en independiente de la validación. Los walk-forward también son retrospectivos a nivel de investigación.
- Comparar menor drawdown contra 100% BTC exagera la utilidad si no se compara además con BTC reducido + efectivo. Ganar dinero, superar a BTC y demostrar alpha son objetivos distintos.

## Recálculo independiente, sin buscar parámetros nuevos

Nuevo motor spot con efectivo y unidades, sin préstamo, entrada en apertura siguiente, comisión de 10 pb + deslizamiento supuesto de 5 pb por lado; estrés de 30 pb totales por lado y demora adicional de 4h. Cobra entrada/salida, incluye capital inicial en drawdown y cierra al final del período. Efectivo rinde cero; sin impuestos. El deslizamiento es un escenario, no una medición de fills reales.

**Candidata: BTC EMA20/100 + SMA200, en velas 4h.** Entrar con todo el capital spot cuando EMA20 > EMA100 y cierre > SMA200. Salir a efectivo si cualquiera falla. Ejecutar desde la apertura siguiente, mantener unidades hasta salir, sin apalancamiento. SMA200 corresponde a aproximadamente 33 días.

| 01-01-2023 a 05-11-2026 | CAGR | Sharpe (rf=0) | Drawdown diario |
|---|---:|---:|---:|
| Candidata BTC, costo 15 pb/lado | 37,1% | 1,15 | -28,7% |
| Misma señal, costo 30 pb/lado | 28,9% | 0,95 | -30,4% |
| Misma señal, entrada demorada otras 4h | 31,3% | 1,01 | -30,4% |
| BTC spot pasivo | 48,6% | 1,09 | -53,0% |
| BTC 61,2% + efectivo, rebalanceo diario | 30,4% | 1,08 | -35,9% |

La exposición del benchmark reducido se calculó con la relación de volatilidades de 2020–2022; no iguala exactamente la volatilidad futura. En validación dio 28,3% de volatilidad frente a 31,8% de la candidata.

La candidata hizo 79 entradas en validación. En 2020–2022 dio 49,8% CAGR y Sharpe 1,12. En 2026 YTD solo 2,4% CAGR; duplicando costos, -3,9%. Un bootstrap pareado de bloques de 30 días (2.000 réplicas, exclusivamente validación) estima diferencia media aritmética anual frente al benchmark reducido de +6,1 puntos, con intervalo 95% **[-17,0; +29,8]**: no demuestra superioridad. Es un intervalo condicional a esta señal, sin corrección por toda la búsqueda previa, y no una probabilidad de que funcione en el futuro.

Recalculé también el voto diario 30/90/180: CAGR 32,8%, Sharpe 0,96, drawdown -34,1%. El rebote de ETH adaptado a spot: 9,0%, 0,91, -7,4%, pero -27,1% CAGR en entrenamiento; no lo priorizaría. Son simulaciones nuevas en spot, no reproducciones idénticas de los contratos perpetuos anteriores.

## Datos y comprobaciones

BTC/ETH spot: 15.005 velas cada uno, sin duplicados ni incoherencias OHLC detectadas; falta una vela de 4h el 19-02-2020 en ambos. Se conserva el hueco y no se inventa precio. Solo se incluyen días hasta el 05-11-2026 completo. Cuatro cierres de muestra (ambos activos en enero 2023 y noviembre 2026) coinciden con consultas nuevas a Binance; esto no certifica todo el historial. Hashes, huecos y pruebas en `audit_checks.json` y `audit_source_samples.json`.

Comprobaciones del motor: precio constante pierde exactamente los costos de entrada/salida; comprar y mantener reproduce el resultado por unidades; modificar precios futuros no cambia señales previas. Todas pasaron. CSV nuevos: `audit_results.csv`, `audit_bootstrap.csv`, `audit_daily_returns.csv`; ejecución: `python audit_backtests.py`.

## Decisión

Congelaría esta regla BTC para observarla con señales/fills nuevos antes de seguir optimizando. Una estrategia útil no necesita batir a BTC en un mercado alcista, pero debe justificar sus costos y riesgo frente a una alternativa simple. La evidencia actual permite una candidata para paper trading; no permite prometer una ganadora ni justificar apalancamiento. El próximo criterio debe ser rentabilidad neta y control de riesgo en datos nuevos, no el mejor resultado de otra grilla sobre los mismos años.

La selección entre muchas pruebas eleva el riesgo de sobreajuste: [Bailey et al., Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf). No se repararon ni recalcularon todos los motores históricos: quedan conservados como exploración, con resultados provisionales, y esta auditoría identifica cuáles requieren reconstrucción.
