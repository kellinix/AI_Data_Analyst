import { chartReaderValueLabels } from '../generated/data-guide';

const scriptJson = (value: unknown) => JSON.stringify(value).replace(/</g, '\\u003c').replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');

export function chartDocumentHeight(option: Record<string, unknown>): number {
  const axis = option.yAxis as { type?: string; data?: unknown[] } | undefined;
  const series = option.series as { type?: string; data?: { name?: unknown; value?: unknown }[] }[] | undefined;
  if (axis?.type === 'category' && series?.some(item => item.type === 'bar')) {
    return Math.max(320, (axis.data?.length ?? 0) * 34 + 80);
  }
  const pie = series?.find(item => item.type === 'pie');
  if (!pie?.data?.some(item => item.name === '')) return 320;
  const labels = chartReaderValueLabels(option).pie;
  const legendHeight = pie.data.reduce((height, item) => {
    const raw = String(item.name ?? '');
    const label = Object.prototype.hasOwnProperty.call(labels, raw) ? labels[raw] : raw || 'Blank value';
    return height + (Math.ceil(label.length / 28) + 1) * 16 + 12;
  }, 16);
  return 240 + legendHeight;
}

/** Chart options are data only. Never eval formatter strings returned by the API. */
export function chartDocument(runtime: string, option: Record<string, unknown>, currency?: string | null): string {
  return `<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'">
<style>html,body,#chart{margin:0;width:100%;height:100%;background:#fff;overflow:hidden}body{font-family:system-ui,sans-serif}</style></head><body><div id="chart"></div>
<script>${runtime.replace(/<\/script/gi, '<\\/script')}</script>
<script>
try {
 const option=${scriptJson(option)};
 const valueLabels=JSON.parse(${scriptJson(JSON.stringify(chartReaderValueLabels(option)))});
 const currency=${scriptJson(currency ?? null)};
 const groupCounts=option._group_counts;
 const percentageValues=option._percentageValues;
 const rangeCounts=Boolean(option._range_count_presentation);
 delete option.title;
 Object.keys(option).forEach(key=>{if(key.startsWith('_'))delete option[key]});
 option.animation=false;
 option.color=['#7950E8','#16B8A6','#FF916B','#E85BB6','#E9B949','#5B8DEF','#8ACF61','#9B7BE8'];
 option.tooltip={...(option.tooltip||{}),renderMode:'richText',confine:true,backgroundColor:'#261D3F',borderColor:'#6D55A0',textStyle:{color:'#FFFFFF',fontSize:12}};
 option.backgroundColor='#fff';
 option.textStyle={...(option.textStyle||{}),fontFamily:'system-ui',fontSize:11,color:'#5F5874'};
 function numeric(value,unit){return new Intl.NumberFormat(undefined,{notation:'compact',maximumFractionDigits:1,...(unit?{style:'currency',currency:unit}:{} )}).format(value)}
 function valueLabel(target,value){const raw=String(value);return Object.prototype.hasOwnProperty.call(valueLabels[target],raw)?valueLabels[target][raw]:raw}
 ['xAxis','yAxis'].forEach(key=>{
   if(!option[key])return;
   const axes=Array.isArray(option[key])?option[key]:[option[key]];
   axes.forEach(axis=>{
     axis.axisLabel={...(axis.axisLabel||{}),hideOverlap:true,color:'#706985'};
     if(rangeCounts&&axis.type==='category')axis.axisLabel={...axis.axisLabel,hideOverlap:false,interval:0,lineHeight:13,formatter:value=>String(value).length>18?String(value).replace(' to ','\\nto '):String(value)};
     if(key==='xAxis'&&axis._monthYearLabels){const labels=axis._monthYearLabels;axis.axisLabel.formatter=value=>labels[String(value)]||String(value);axis.name=axis.name||'Month';delete axis._monthYearLabels;}
     axis.axisLine={...(axis.axisLine||{}),lineStyle:{color:'#E8E1F1'}};
     if(axis.type==='value')axis.splitLine={show:true,lineStyle:{color:'#ECE7F3',type:'dashed'}};
     const axisCurrency=axis._currency||((option.series||[]).some(series=>series.type==='scatter')?null:currency);
     if(axis.type==='value'||axis.type==='log')axis.axisLabel.formatter=axis._percentage?value=>Math.round(value*100)+'%':value=>numeric(value,axisCurrency);
     if(axis.type==='category'&&Object.keys(valueLabels[key]).length)axis.axisLabel.formatter=value=>valueLabel(key,value);
   });
 });
 if(rangeCounts)(option.series||[]).forEach(series=>{series.label={...(series.label||{}),formatter:params=>new Intl.NumberFormat().format(params.value)}});
 (option.series||[]).forEach(series=>{
   if(series.type!=='pie')return;
   const donut=Array.isArray(series.radius)&&series.radius[0]!==0&&series.radius[0]!=='0%';
   series.radius=donut?['28%','48%']:'48%';
   series.center=['50%','46%'];
   series.avoidLabelOverlap=true;
   series.label={...(series.label||{}),show:true,position:'outside',color:'#5F5874',fontSize:10,width:80,overflow:'break',lineHeight:14,edgeDistance:6,alignTo:'edge',formatter:params=>valueLabel('pie',params.name)+'\\n'+new Intl.NumberFormat(undefined,{maximumFractionDigits:2,...(currency?{style:'currency',currency}:{})}).format(params.value)+' ('+Number(params.percent).toFixed(1)+'%)'};
   series.labelLine={show:true,length:10,length2:6,lineStyle:{color:'#A39BB7'}};
   series.labelLayout={hideOverlap:true};
 });
 if(groupCounts){option.grid={...(option.grid||{}),left:40,right:110,containLabel:true};(option.series||[]).forEach(series=>{if(series.type==='bar')series.label={show:true,position:'right',fontSize:10,color:'#5F5874',formatter:params=>new Intl.NumberFormat(undefined,{maximumFractionDigits:2}).format(params.value)+(percentageValues?'%':'')+' ('+groupCounts[params.name]+(groupCounts[params.name]===1?' record)':' records)')}});}
 const horizontalBar=option.yAxis&&option.yAxis.type==='category'&&(option.series||[]).some(series=>series.type==='bar');
 const pie=(option.series||[]).find(series=>series.type==='pie');
 const externalPieLegend=pie&&(pie.data||[]).some(item=>item.name==='');
 let smallScreenOption={};
 if(horizontalBar){
   option.xAxis={...option.xAxis,nameLocation:'middle',nameGap:38};
   smallScreenOption={
     grid:{left:8,right:56,top:16,bottom:60,containLabel:true},
     yAxis:{axisLabel:{width:112,overflow:'break',lineHeight:14,interval:0,margin:8}},
     series:option.series.map(series=>({...series,label:{...(series.label||{}),fontSize:10,
       formatter:params=>numeric(params.value,currency)+(percentageValues?'%':'')}}))
   };
   if(groupCounts)option.tooltip.formatter=params=>{
     const first=params[0];
     if(!first)return '';
     return String(first.name)+'\\n'+String(first.seriesName)+' '+new Intl.NumberFormat(undefined,{maximumFractionDigits:2,...(currency?{style:'currency',currency}:{})}).format(first.value)+(percentageValues?'%':'')+'\\n'+groupCounts[first.name]+' entries with a supplied value';
   };
 } else if(pie){
   const data=pie.data||[];
   const total=data.reduce((sum,item)=>sum+Number(item.value||0),0);
   smallScreenOption={
     legend:{show:!externalPieLegend,selectedMode:false,left:0,right:0,bottom:4,itemWidth:10,itemHeight:10,itemGap:12,
       textStyle:{color:'#5F5874',fontSize:11,lineHeight:16},
       formatter:name=>{
         const item=data.find(value=>value.name===name);
         const value=Number(item?item.value:0);
         return valueLabel('pie',name)+'\\n'+new Intl.NumberFormat(undefined,{maximumFractionDigits:2}).format(value)+' ('+(total?value/total*100:0).toFixed(1)+'%)';
       }},
     series:option.series.map(series=>({...series,center:externalPieLegend?['50%','50%']:['50%','32%'],radius:externalPieLegend?['28%','55%']:['24%','48%'],label:{show:false},labelLine:{show:false}}))
   };
 }
 if(externalPieLegend){
   option.legend={show:false};
   pie.center=['50%','50%'];pie.radius=['28%','55%'];pie.label={show:false};pie.labelLine={show:false};
   document.body.style.display='flex';document.body.style.flexDirection='column';
   const container=document.getElementById('chart');
   container.style.flex='1';container.style.minHeight='0';container.style.height='auto';
   const legend=document.createElement('div');
   legend.setAttribute('role','list');legend.setAttribute('aria-label','Chart categories');
   Object.assign(legend.style,{display:'flex',flexWrap:'wrap',gap:'12px',padding:'8px',flexShrink:'0',fontSize:'11px',lineHeight:'16px',color:'#5F5874'});
   const total=pie.data.reduce((sum,item)=>sum+Number(item.value||0),0);
   pie.data.forEach((item,index)=>{
     const row=document.createElement('div');row.setAttribute('role','listitem');
     Object.assign(row.style,{display:'flex',alignItems:'flex-start',gap:'6px',maxWidth:'100%',minWidth:'0'});
     const marker=document.createElement('span');
     Object.assign(marker.style,{width:'8px',height:'8px',marginTop:'4px',flexShrink:'0',backgroundColor:item.itemStyle&&item.itemStyle.color||option.color[index%option.color.length]});
     const text=document.createElement('span');
     Object.assign(text.style,{whiteSpace:'pre-line',overflowWrap:'anywhere'});
     const amount=Number(item.value||0);
     text.textContent=(valueLabel('pie',item.name)||'Blank value')+'\\n'+new Intl.NumberFormat(undefined,{maximumFractionDigits:2,...(currency?{style:'currency',currency}:{})}).format(amount)+' ('+(total?amount/total*100:0).toFixed(1)+'%)';
     row.appendChild(marker);row.appendChild(text);legend.appendChild(row);
   });
   document.body.appendChild(legend);
 }
 if(Object.keys(valueLabels.series).length)option.legend={...(option.legend||{}),formatter:name=>valueLabel('series',name)};
 if(Object.values(valueLabels).some(labels=>Object.keys(labels).length)){
   option.tooltip.formatter=parameters=>{
     const items=Array.isArray(parameters)?parameters:[parameters];
     const first=items[0];
     if(!first)return '';
     const number=value=>new Intl.NumberFormat(undefined,{maximumFractionDigits:2,...(currency?{style:'currency',currency}:{})}).format(value);
     if(pie)return valueLabel('pie',first.name)+'\\n'+number(first.value)+' ('+Number(first.percent||0).toFixed(1)+'%)';
     const rows=items.map(item=>(valueLabel('series',item.seriesName||'')+' '+number(item.value)+(percentageValues?'%':'')).trim());
     if(groupCounts&&groupCounts[first.name]!==undefined)rows.push(groupCounts[first.name]+' entries with a supplied value');
     return [valueLabel(horizontalBar?'yAxis':'xAxis',first.name),...rows].join('\\n');
   };
 }
 option.media=[{query:{maxWidth:480},option:smallScreenOption}];
 if(option.yAxis&&option.yAxis._percentage)option.tooltip.formatter=params=>'Grade average: '+params.value[0]+'\\nRecorded admission chance: '+new Intl.NumberFormat(undefined,{maximumFractionDigits:2}).format(params.value[1]*100)+'%';
 const chart=echarts.init(document.getElementById('chart'));
 chart.setOption(option);
 window.addEventListener('resize',()=>chart.resize());
} catch(error) {
 document.getElementById('chart').textContent='This chart could not be displayed.';
 if(window.ReactNativeWebView)window.ReactNativeWebView.postMessage('chart-error');
}
</script></body></html>`;
}
