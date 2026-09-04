# SMC K-line Signal Visualization — V16.2 序列标记

## 核心需求
选股页点击跳转到K线图时，图表上必须清晰标出SMC信号序列的每个信号位置，
让用户一眼看出"触发的是哪个信号"、"信号是否在对的位置"。

## 实现方式

### URL参数传递
选股页跳转链接携带 `&seq=` 参数:
```
/kline?s=000507_SZ&seq=OB→CH→PB→IDM
```

### JavaScript序列解析
```javascript
function parseSeqFromURL(){
    var p=new URLSearchParams(window.location.search);
    var s=p.get('seq')||'';
    return s.split(/->|→|-/).filter(function(x){return x.length>0});
}
currentSeq=parseSeqFromURL();
```
- 分隔符: `→`, `->`, 或 `-`
- 结果: `['OB', 'CH', 'PB', 'IDM']`

### 信号→序列编号映射
```javascript
var seqMap={};  // signal_type → 序列位置(1-based)
if(t==='LIQ'){seqMap['Sweep_SSL']=i+1;seqMap['Sweep_BSL']=i+1;}
else if(t==='OB'){seqMap['OB_Bull']=i+1;seqMap['OB_Bear']=i+1;}
else if(t==='CH'){seqMap['CHOCH_Bull']=i+1;seqMap['CHOCH_Bear']=i+1;}
// ... FVG, PB, BRK, MSS, IDM, TS
```

### 三层标记体系
| 匹配级别 | 符号 | 大小 | 颜色 | 标签 | 位置 |
|----------|------|------|------|------|------|
| 序列匹配 | `pin` 图钉 | 12px | 鲜红 #ff1744 | ①LIQ ②OB | top |
| 关键SMC | `diamond` 菱形 | 10px | 红 #f85149 | LIQ OB CH | inside |
| 普通信号 | `circle` 圆 | 6px | 类型色 | 序号 | inside |

### Unicode 序列编号
```javascript
if(seqNum>0){
    var cn=String.fromCharCode(0x245F+seqNum);  // ①=0x2460, ②=0x2461, ...
    label=cn+sl;  // '①LIQ', '②OB', '③CH'
}
```
- 支持 ①-⑨ (seqNum 1-9), SMC序列通常2-5个元素足够

## 渲染函数: `buildSignalPoints(af)` 
位于 `smc_unified.py` 的 `KLINE_FULL_JS` JavaScript块。
- 输入: `allSeries` (全局信号数组), `currentSeq` (URL序列数组)
- 序列信号: 越早匹配越优先, 相同信号类型可能多个但编号相同
- 关键信号: 按 `seqLabels` 字典匹配, 未匹配的通用信号显示数字序号

## 依赖
- `smc_unified.py` 中的 `KLINE_FULL_JS` 变量
- 选股页跳转链接需携带 `&seq=` 参数（dashboard/monitor/build_rows均已添加）
- `parseSeqFromURL()` + `currentSeq` 全局变量
