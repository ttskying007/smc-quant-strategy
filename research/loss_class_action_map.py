# -*- coding: utf-8 -*-
"""R13/R20 分类→闭环动作表
与 audit_handover artifact 相匹配，倒Lead每类标签映射"可执行 第一步→ 完成状态"
"""
import io, json, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

TABLE = [
    ('LOSS_OTHER',              0.0,  '当前 n=14 / 小型尚无二义', True),
    ('LOSS_EXECUTION_COST',     0.0,  'n=4 不参与决策 (net ~-0.3)', False),
    ('LOSS_TIME_STOP',          0.0,  'n=2 身份与风险联动', True),
    ('LOSS_MEDIUM',             0.0,  'mayer 样本掉落 at takedown 6 (设计)', False),
    ('LOSS_HIGH_RANK',          1.4,  'n=94 +5.5% - 需要 OOS 的当日 rank>=4 警戒 (正确变量是 reverser 一度被反了)', False),
    ('LOSS_LOW_RANK',           3.0,  'n=37(微调后 rank<3 为名义)——原始 rank<=3 gate 阻止正常入场', False),
    ('LOSS_MFE_REVERSAL',       0.6,  'n=47 (5.5%) MFE>=1R 仍未出局，需 deferred 申必 + 节气功率提', False),
    ('LOSS_SL_STRUCTURAL',      0.4,  'n=33(6.2%) 寺内止损0.6~3×ATR - 结构性轻单', True),
    ('LOSS_SL_TOO_WIDE',        2.2,  'n=244 (46%) SL=invalid-1.5ATR is design intent', True),
    ('LOSS_SL_TOO_TIGHT',       0.8,  'n=55 SL<0.6×ATR=SL_TOO_TIGHT-tooclose 固定基础', True),
    ('LOSS_TIME_SHORT',         0.5,  'n=59 (10.9%) 入场后 <=2bar 触发 SL → v2_delay1_ab 已否决 1-bar延迟', True),
    ('LOSS_TIME_LONG',          0.7,  'n=30 (5.1%): R17 月度圈地 LOS 10 秒台拉用力', False),
]

def main():
    matrix = []
    for name, q, note, is_closed in TABLE:
        matrix.append({
            'class': name, 'importance_score': q, 'note': note, 'closed': is_closed
        })
    out = {
        'asof': __import__('time').strftime('%Y-%m-%d %H:%M:%S'),
        'purpose': '亏损分类→关闭状态的纲目 (R13 → R18)',
        'rows': matrix
    }
    os.makedirs('research/handover', exist_ok=True)
    with open(r'research/handover/loss_class_action_map.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    for r in matrix:
        print(f"  {'CLOSED' if r['closed'] else 'OPEN  '}  {r['class']:<24s} {r['note']}")
    # 筛选工艺 per bucket
    total_blocked = sum(1 for m in matrix if m['closed'])
    print(f"\n{len(matrix)} classes: {total_blocked} closed / {len(matrix) - total_blocked} active")
    print("\nRemaining ACTIV classes(后续深化):")
    act = [m for m in matrix if not m['closed']]
    for a in act:
        print('  -', a['class'], '|', a['note'])

if __name__ == '__main__':
    main()
