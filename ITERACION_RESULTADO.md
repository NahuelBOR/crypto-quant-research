# Candidata nueva: tendencia confirmada y exposición por volatilidad

**Resultado exploratorio prometedor, sin garantía ni validación ciega.** Se usó el motor auditado de efectivo/unidades en spot, con comisiones y deslizamiento supuestos. No reutilicé los motores de futuros/carry cuestionados.

## Qué probé

La tanda 02 incluyó 16 variantes nuevas y la EMA original: bandas de entrada/salida, confirmación de señales, rupturas de canales, trailing stop basado en ATR, exposición por votos de varios plazos, sizing por volatilidad, compras de retrocesos y reentrada tras máximos locales. El ganador por entrenamiento fue un canal de 240 velas: solo rindió 15,8% CAGR en BTC después de 2022. La selección anual de tres familias produjo 27,0% CAGR y Sharpe 0,98; no mejoró la EMA original. Conservo estas pruebas fallidas en `iteration_02_results`.

La tanda 03 combinó dos mecanismos prometedores de esa exploración: confirmar la tendencia y reducir exposición cuando aumenta la volatilidad. Comparé 3/6 velas de confirmación y tamaños basados en volatilidad del 30%/45%: cuatro combinaciones. Elegí usando el Sharpe de BTC 2020–2022 con costos duplicados y trasladé la misma regla a ETH. **El diseño de esta tanda sí usó lo visto en la tanda anterior; no es un descubrimiento independiente de 2023–2026.**

## Regla exacta congelada

1. Dividir inicialmente el capital en dos cuentas: 50% BTC y 50% ETH. Cada cuenta opera independientemente, sin redistribuir ganancias entre ellas.
2. En velas de 4h, condición favorable = EMA20 > EMA100 y cierre > SMA200. Entrar después de 3 cierres consecutivos favorables. Salir después de 3 cierres consecutivos desfavorables. Ejecutar en apertura siguiente.
3. Cada domingo al cierre de la vela de las 20 UTC, estimar volatilidad con los últimos 180 retornos de 4h, anualizados con √(6×365,25). Tamaño deseado = mínimo(1; 0,30/volatilidad), redondeado al múltiplo más próximo de 25%. El resto queda en efectivo sin interés.
4. Aplicar ese tamaño mientras esté activa la tendencia, y cero al salir. Operar cuando cambie el tamaño deseado; si no cambia, mantener unidades. La fracción real deriva con el precio: **no es un objetivo de volatilidad garantizado**. SMA200 son unas 33 jornadas. Sin préstamo, short ni apalancamiento.

## Resultado 01-01-2023 a 05-11-2026

| Cartera | CAGR | Sharpe, rf=0 | Caída máxima diaria |
|---|---:|---:|---:|
| Candidata BTC/ETH | 28,7% | 1,24 | -23,5% |
| Costos duplicados | 25,4% | 1,12 | -24,9% |
| Costos duplicados + 4h extra de demora | 25,2% | 1,11 | -22,6% |
| Comprar BTC/ETH, 50/50 inicial | 35,6% | 0,87 | -57,6% |
| Mitad cripto, mitad efectivo; rebalanceo diario en cada cuenta | 19,6% | 0,83 | -34,3% |

Costo base: 10 pb de comisión + 5 pb de deslizamiento por lado; estrés: 30 pb totales. Se cobra cada operación real de cambio de unidades y cierre final. Cifras netas de esos supuestos, sin impuestos. Drawdown medido al cierre diario; puede ser peor intradía.

Retornos efectivos de la candidata: **2023 +49,4%; 2024 +54,3%; 2025 +2,6%; 2026 hasta 05/11 +11,7%**. Las ganancias están concentradas en los primeros dos años. BTC solo perdió 5,8% en 2025. Hubo 48 entradas BTC y 44 ETH en validación, más operaciones de ajuste de tamaño.

Por separado, BTC dio 32,8% CAGR / Sharpe 1,28; ETH, 24,3% / 0,98. Con costos dobles siguieron positivos: 28,9% y 21,5%. La variante de volatilidad 45% y las confirmaciones de 6 velas también se ejecutaron; todas las variantes constan en `iteration_03_results/results.csv`.

## Cuánta confianza merece

Es una mejora histórica de retorno/riesgo frente al benchmark mitad cripto/mitad efectivo, **no alpha demostrada**. El bootstrap pareado con bloques de 30 días (2.000 réplicas) da diferencia media aritmética anual de +6,7 puntos, intervalo 95% **[-11,2; +26,3]**. Incluye cero y no corrige toda la selección previa. La referencia calibrada por volatilidad de entrenamiento tuvo menor riesgo real en validación; por eso también incluí el benchmark sencillo mitad cripto/mitad efectivo.

Comprobé que modificar datos futuros no altere señales previas y reutilicé las identidades contables del motor auditado. Datos y hueco histórico documentados en `REVISION_AUDITORIA.md`. Los planes/CSV de cada tanda se conservan por separado. No hay simulación de profundidad, fills reales ni resultados nuevos posteriores a este historial.

**Decisión:** congelar `confirm3_vol0.3` como candidata experimental y exigir datos nuevos antes de aumentar confianza. Reproducción: `python iteration_02.py`, `python iteration_03.py`, `python iteration_03_portfolio.py`. No se activaron operaciones reales.
