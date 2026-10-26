const scriptJson = (value: unknown) => JSON.stringify(value).replace(/</g, '\\u003c').replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');

/** Chart options are data only. Never eval formatter strings returned by the API. */
export function chartDocument(runtime: string, option: Record<string, unknown>, currency?: string | null): string {
  return `<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'">
<style>html,body,#chart{margin:0;width:100%;height:100%;background:#fff;overflow:hidden}body{font-family:system-ui,sans-serif}</style></head><body><div id="chart"></div>
<script>${runtime.replace(/<\/script/gi, '<\\/script')}</script>
<script>
try {
 const option=${scriptJson(option)};
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
 function numeric(value){return new Intl.NumberFormat(undefined,{notation:'compact',maximumFractionDigits:1,...(currency?{style:'currency',currency}:{} )}).format(value)}
 ['xAxis','yAxis'].forEach(key=>{
   if(!option[key])return;
   const axes=Array.isArray(option[key])?option[key]:[option[key]];
   axes.forEach(axis=>{
     axis.axisLabel={...(axis.axisLabel||{}),hideOverlap:true,color:'#706985'};
     if(rangeCounts&&axis.type==='category')axis.axisLabel={...axis.axisLabel,hideOverlap:false,interval:0,lineHeight:13,formatter:value=>String(value).length>18?String(value).replace(' to ','\\nto '):String(value)};
     if(key==='xAxis'&&axis._monthYearLabels){const labels=axis._monthYearLabels;axis.axisLabel.formatter=value=>labels[String(value)]||String(value);axis.name='Month';delete axis._monthYearLabels;}
     axis.axisLine={...(axis.axisLine||{}),lineStyle:{color:'#E8E1F1'}};
     if(axis.type==='value')axis.splitLine={show:true,lineStyle:{color:'#ECE7F3',type:'dashed'}};
     if(axis.type==='value'||axis.type==='log')axis.axisLabel.formatter=axis._percentage?value=>Math.round(value*100)+'%':numeric;
   });
 });
 if(rangeCounts)(option.series||[]).forEach(series=>{series.label={...(series.label||{}),formatter:params=>new Intl.NumberFormat().format(params.value)}});
 (option.series||[]).forEach(series=>{
   if(series.type!=='pie')return;
   const donut=Array.isArray(series.radius)&&series.radius[0]!==0&&series.radius[0]!=='0%';
   series.radius=donut?['28%','48%']:'48%';
   series.center=['50%','46%'];
   series.avoidLabelOverlap=true;
   series.label={...(series.label||{}),show:true,position:'outside',color:'#5F5874',fontSize:10,width:80,overflow:'break',lineHeight:14,edgeDistance:6,alignTo:'edge',formatter:params=>String(params.name)+'\\n'+new Intl.NumberFormat(undefined,{maximumFractionDigits:2,...(currency?{style:'currency',currency}:{})}).format(params.value)+' ('+Number(params.percent).toFixed(1)+'%)'};
   series.labelLine={show:true,length:10,length2:6,lineStyle:{color:'#A39BB7'}};
   series.labelLayout={hideOverlap:true};
 });
 if(groupCounts){option.grid={...(option.grid||{}),left:40,right:110,containLabel:true};(option.series||[]).forEach(series=>{if(series.type==='bar')series.label={show:true,position:'right',fontSize:10,color:'#5F5874',formatter:params=>new Intl.NumberFormat(undefined,{maximumFractionDigits:2}).format(params.value)+(percentageValues?'%':'')+' ('+groupCounts[params.name]+(groupCounts[params.name]===1?' applicant)':' applicants)')}});}
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
