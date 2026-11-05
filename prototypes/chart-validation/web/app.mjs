import { createChart, LineSeries, LineStyle, LineType, ColorType } from '/charts.mjs';
import { segments, nearestIndex, formattedDate, formattedValue } from './model.mjs';
await Promise.all([document.fonts.load('500 22px "Space Grotesk"'), document.fonts.load('400 16px Inter')]);
const bundle = await fetch('/fixtures.json').then(response => response.json());
const visualStyle = await fetch('/visual-style.json').then(response => response.json());
const $ = id => document.getElementById(id);
const words = {
  en: { synthetic:'SYNTHETIC EXAMPLE', prototype:'CHART PROTOTYPE', heading:'A clear view of each point', intro:'Synthetic examples for chart interaction testing.', scenario:'Example', language:'Language', appearance:'Appearance', system:'System', light:'Light', dark:'Dark', actual:'Actual', projected:'Projected', contribution:'Contribution', empty:'No points in this example', instructions:'Drag left or right to inspect. Scroll up or down to move the page. Buttons inspect every point.', previous:'Previous', next:'Next', reset:'Reset', select:'Choose a point with the chart or buttons.', notes:'About these examples', truth:'Synthetic data only. Lines stop at missing values. Dashed projections are supplied examples, not calculated forecasts.', scroll:'This space lets you test vertical page scrolling while your finger starts on the chart.', unit:'Major currency units · civil dates in UTC', none:'No selection' },
  'es-419': { synthetic:'EJEMPLO SINTÉTICO', prototype:'PROTOTIPO DE GRÁFICA', heading:'Cada punto, con claridad', intro:'Ejemplos sintéticos para probar la interacción con gráficas.', scenario:'Ejemplo', language:'Idioma', appearance:'Apariencia', system:'Sistema', light:'Claro', dark:'Oscuro', actual:'Real', projected:'Proyectado', contribution:'Aportación', empty:'Este ejemplo no tiene puntos', instructions:'Arrastra a los lados para consultar. Desliza arriba o abajo para mover la página. Los botones recorren cada punto.', previous:'Anterior', next:'Siguiente', reset:'Restablecer', select:'Elige un punto en la gráfica o con los botones.', notes:'Sobre estos ejemplos', truth:'Solo datos sintéticos. Las líneas se interrumpen donde faltan datos. Las proyecciones son ejemplos proporcionados, no pronósticos calculados.', scroll:'Este espacio permite probar el desplazamiento vertical iniciando sobre la gráfica.', unit:'Unidades monetarias principales · fechas civiles en UTC', none:'Sin selección' },
};
let locale = 'en', selected = null, scenario = bundle.cases[0], drag = null, plotted = [];
const media = matchMedia('(prefers-color-scheme: dark)');
const metrics = { renders: [], selections: [] };
const chart = createChart($('chart'), {
  autoSize: true,
  handleScroll: false, handleScale: false,
  crosshair: { vertLine:{visible:false}, horzLine:{visible:false} },
  rightPriceScale:{borderVisible:false},
  timeScale:{borderVisible:false, fixLeftEdge:true, fixRightEdge:true, minBarSpacing:0.01},
  layout:{attributionLogo:false,fontFamily:'Inter, Arial, sans-serif',fontSize:12},
});
const anchor = chart.addSeries(LineSeries, { visible:false });
function theme() {
  const dark = $('theme').value === 'dark' || ($('theme').value === 'system' && media.matches);
  document.documentElement.dataset.dark = String(dark);
  for (const key of ['actual','projected']) document.documentElement.style.setProperty(`--${key}`,visualStyle[dark?'dark':'light'][key]);
  const css = getComputedStyle(document.documentElement);
  chart.applyOptions({ layout:{background:{type:ColorType.Solid, color:css.getPropertyValue('--surface').trim()},textColor:css.getPropertyValue('--muted').trim()}, grid:{vertLines:{visible:false},horzLines:{color:css.getPropertyValue('--grid').trim()}} });
  for (const {series,key} of plotted) series.applyOptions({color:css.getPropertyValue(`--${key}`).trim()});
}
function text() {
  const copy = words[locale];
  document.documentElement.lang = locale;
  for (const node of document.querySelectorAll('[data-text]')) node.textContent = copy[node.dataset.text];
  $('scenario').replaceChildren(...bundle.cases.map(item => new Option(item.title[locale],item.id,false,item.id === scenario.id)));
  $('case-title').textContent = scenario.title[locale];
  $('currency').textContent = scenario.currency;
  $('unit').textContent = `${scenario.currency} · ${copy.unit}`;
  $('scrub').setAttribute('aria-label',locale === 'en' ? 'Chart touch surface' : 'Área táctil de la gráfica');
  chart.applyOptions({localization:{locale:locale === 'en'?'en-US':'es-419', priceFormatter:value => formattedValue(value,scenario.currency,locale), timeFormatter:time => formattedDate(typeof time==='string'?time:`${time.year}-${String(time.month).padStart(2,'0')}-${String(time.day).padStart(2,'0')}`,locale)}});
  readout();
}
function readout() {
  const start = performance.now();
  const copy = words[locale], point = scenario.points[selected];
  $('readout').replaceChildren();
  if (selected === null) $('readout').textContent = scenario.points.length ? copy.select : copy.empty;
  else {
    const date = document.createElement('strong');
    date.textContent = formattedDate(point.time,locale);
    $('readout').append(date);
    for (const key of ['actual','projected','contribution']) {
      const row = document.createElement('p');
      row.dataset.field = key;
      row.textContent = `${copy[key]}: ${formattedValue(point[key],scenario.currency,locale)}`;
      $('readout').append(row);
    }
  }
  $('readout').dataset.index = selected === null ? '' : String(selected);
  $('readout').dataset.date = selected === null ? '' : point.time;
  $('previous').disabled = !scenario.points.length || selected === 0;
  $('next').disabled = !scenario.points.length || selected === scenario.points.length - 1;
  $('reset').disabled = selected === null;
  positionLine();
  metrics.selections.push(performance.now()-start);
}
function positionLine() {
  $('selection-line').hidden = selected === null;
  if (selected !== null) $('selection-line').style.left = `${chart.timeScale().timeToCoordinate(scenario.points[selected].time)}px`;
}
function render() {
  const start = performance.now(), scenarioId = scenario.id;
  for (const {series} of plotted) chart.removeSeries(series);
  plotted = [];
  anchor.setData(scenario.points.map(({time})=>({time})));
  for (const key of ['actual','projected']) {
    for (const data of segments(scenario.points,key)) {
      const series = chart.addSeries(LineSeries, {lineWidth:2,lineVisible:data.length>1,lineType:LineType.Simple,lineStyle:key === 'actual'?LineStyle.Solid:LineStyle.Dashed,pointMarkersVisible:scenario.points.length < 100 || data.length === 1,pointMarkersRadius:3,lastValueVisible:false,priceLineVisible:false,crosshairMarkerVisible:false});
      series.setData(data);
      plotted.push({series,key});
    }
  }
  $('empty').hidden = scenario.points.length > 0;
  text(); theme(); chart.timeScale().fitContent();
  requestAnimationFrame(()=>requestAnimationFrame(()=>{positionLine();metrics.renders.push({scenario:scenarioId,ms:performance.now()-start});}));
}
function selectAt(event) {
  const x = event.clientX - $('scrub').getBoundingClientRect().left;
  selected = nearestIndex(chart.timeScale().coordinateToLogical(x),scenario.points.length);
  readout();
}
$('scrub').addEventListener('pointerdown', event => {
  if (event.button !== 0 || !event.isPrimary) return;
  drag = {id:event.pointerId,x:event.clientX,y:event.clientY,prior:selected,axis:null};
});
$('scrub').addEventListener('pointermove', event => {
  if (!drag || drag.id !== event.pointerId) return;
  const dx = Math.abs(event.clientX-drag.x), dy=Math.abs(event.clientY-drag.y);
  if (!drag.axis && Math.max(dx,dy)>6) {
    drag.axis = dx>dy?'horizontal':'vertical';
    if (drag.axis === 'horizontal') $('scrub').setPointerCapture(event.pointerId);
  }
  if (drag.axis === 'horizontal') selectAt(event);
});
window.addEventListener('pointerup', event => {
  if (!drag || drag.id!==event.pointerId) return;
  if (!drag.axis) selectAt(event);
  drag = null;
});
function cancel(event) {
  if (!drag || drag.id!==event.pointerId) return;
  selected=drag.prior;drag=null;readout();
}
window.addEventListener('pointercancel',cancel);
$('scrub').addEventListener('lostpointercapture',cancel);
$('previous').onclick=()=>{selected=selected===null?scenario.points.length-1:Math.max(0,selected-1);readout();};
$('next').onclick=()=>{selected=selected===null?0:Math.min(scenario.points.length-1,selected+1);readout();};
$('reset').onclick=()=>{selected=null;readout();};
$('scenario').onchange=()=>{scenario=bundle.cases.find(item=>item.id===$('scenario').value);selected=null;drag=null;render();};
$('locale').onchange=()=>{locale=$('locale').value;text();};
$('theme').onchange=theme;
media.addEventListener('change',theme);
new ResizeObserver(positionLine).observe($('chart'));
render();
// Local prototype observability: no network collector or production instrumentation.
window.chartPrototype = { metrics, get state(){return {scenario:scenario.id, selected, segmentCount:plotted.length, points:scenario.points.length};}, coordinate(index){return chart.timeScale().timeToCoordinate(scenario.points[index].time);} };
