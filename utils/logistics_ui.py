"""Monthly logistics editor; calculations never alter campaign state."""
from copy import deepcopy
import tkinter as tk
from tkinter import ttk, messagebox
from calculators.campaign import ForceRecord, ElementRecord
from calculators.logistics import LogisticsInput, SupplyGroup, LogisticsEngine
from utils.gui_editors import EditorWindow
from utils.editor_records import number
from utils.i18n import t


class LogisticsEditor(EditorWindow):
    def __init__(self, app, side='attacker'):
        if side not in ('attacker', 'defender'):
            raise ValueError('invalid_logistic_input')
        super().__init__(app, 'log_ui_title')
        self.side = side
        self.key = 'gui.mass.' + side
        self.snapshot = deepcopy(app.campaign_session.to_dict())
        self.pending = None
        self.displays = []
        self.values = {}
        self.flags = {}
        saved = app.campaign_session.logistics_plans.get(self.key, {})
        group = saved.get('groups', [{}])[0]
        force = app.campaign_session.forces.get(self.key)
        ttk.Label(self.form, text=t('log_ui_help', side=t('mass_aftermath_side_' + side)), wraplength=720).grid(row=0,column=0,columnspan=2,sticky='w')
        entries = [('monthly_cost',group.get('monthly_cost',0)),('funds',force.resources if force else 0),
            ('administration',saved.get('administration',10)),('administration_roll',''),('tl',group.get('tl',8))]
        strengths = app.campaign_session.force_logistic_strengths.get(self.key,{})
        for kind in ('land','naval','air'):
            entries += [('ls_'+kind,strengths.get(kind,0)),('tl_'+kind,saved.get('logistic_tl',{}).get(kind,8))]
        for row, (key, value) in enumerate(entries,1):
            self.values[key] = tk.StringVar(self,value=str(value))
            self.entry(row,t('log_ui_'+key),self.values[key])
        row = len(entries)+1
        for key, choices, default in [('domain',('land','naval','air'),'land'),
            ('readiness',('full','low','none'),'full'),
            ('terrain',('clear','arctic','desert','jungle','mountain','swampland','woodlands'),'clear')]:
            canonical=tk.StringVar(self,value=group.get(key,default))
            self.values[key]=canonical
            labels={t('log_value_'+v):v for v in choices}
            display=tk.StringVar(self,value=t('log_value_'+canonical.get()))
            self.displays.append(display)
            ttk.Label(self.form,text=t('log_ui_'+key)).grid(row=row,column=0,sticky='w',pady=4)
            box=ttk.Combobox(self.form,textvariable=display,values=tuple(labels),state='readonly')
            box.grid(row=row,column=1,sticky='ew',padx=8)
            box.bind('<<ComboboxSelected>>',lambda event,c=canonical,d=display,m=labels:c.set(m[d.get()]))
            row+=1
        for key in ('terrain_feature','transport_network','land_supply_line','naval_base','airbase',
                    'land_via_port','inland_sea_supply','campaign_season','rural'):
            value=group.get(key,False) if key in ('terrain_feature','transport_network') else saved.get(key,key=='land_supply_line')
            self.flags[key]=tk.BooleanVar(self,value=value)
            ttk.Checkbutton(self.form,text=t('log_ui_'+key),variable=self.flags[key]).grid(row=row,column=0,columnspan=2,sticky='w')
            row+=1
        self.output=ttk.Label(self.form,text='',wraplength=720,justify='left')
        self.output.grid(row=row,column=0,columnspan=2,sticky='w',pady=12)
        self.action('log_ui_save',self.save_configuration)
        self.action('common_calculate',lambda:self.run(False))
        self.action('common_resolve',lambda:self.run(True))
        self.action('log_ui_apply',self.apply_month)

    def inputs(self):
        return tuple(v.get() for v in self.values.values())+tuple(v.get() for v in self.flags.values())

    def force(self):
        existing=self.app.campaign_session.forces.get(self.key)
        if existing is not None:return deepcopy(existing)
        return ForceRecord(self.key,self.side,[ElementRecord(self.side,self.side,
            number(getattr(self.app,'mass_'+self.side+'_ts').get(),float),['Inf'])],
            commander_strategy=number(getattr(self.app,'mass_'+self.side+'_strategy').get(),int))

    def data(self):
        vals=self.values
        flags={k:v.get() for k,v in self.flags.items()}
        group=SupplyGroup(self.key,number(vals['monthly_cost'].get(),float),domain=vals['domain'].get(),
            tl=number(vals['tl'].get(),int),terrain=vals['terrain'].get(),readiness=vals['readiness'].get(),
            recovering=self.force().readiness_recovering,
            terrain_feature=flags.pop('terrain_feature'),transport_network=flags.pop('transport_network'))
        return LogisticsInput(groups=[group],strengths={k:number(vals['ls_'+k].get(),float) for k in ('land','naval','air')},
            logistic_tl={k:number(vals['tl_'+k].get(),int) for k in ('land','naval','air')},
            funds=number(vals['funds'].get(),float),administration=number(vals['administration'].get(),int),
            administration_roll=number(vals['administration_roll'].get(),int) if vals['administration_roll'].get().strip() else None,**flags)

    def save_configuration(self):
        data=self.data()
        LogisticsEngine().validate(data)
        if not messagebox.askyesno(t('log_ui_save'),t('log_ui_save_confirm'),parent=self):return
        self.app.campaign_session.configure_logistics(self.force(),data,self.snapshot)
        self.snapshot=deepcopy(self.app.campaign_session.to_dict())
        self.pending=None
        self.app._pending_mass_round=None
        self.output.configure(text=t('log_ui_saved'))

    def run(self, resolve):
        self.pending=None
        if self.app.campaign_session.to_dict()!=self.snapshot:raise ValueError('stale_battle_result')
        data=self.data()
        engine=LogisticsEngine()
        result=engine.resolve(data) if resolve else engine.calculate(data)
        effect=result.effects[self.key]
        lines=[t('log_ui_summary',raise_cost=sum(result.raise_costs.values()),logistics=sum(result.logistic_costs.values()),
                 combat=sum(result.group_costs.values()),total=result.total_cost,capacity=result.capacity_shortfall),
               t('log_ui_effect',multiplier=effect['ts_multiplier'],loss=effect['casualties']),
               t('log_ui_admin_result',roll=result.roll if result.roll is not None else '—',factor=result.administration_factor)]
        lines.extend(t(error) for error in result.errors)
        if result.pending:lines.append(t('log_ui_pending'))
        lines.append('Mass Combat, pp. 13–14')
        self.output.configure(text='\n'.join(lines))
        if result.complete:self.pending=(data,result,self.inputs())

    def apply_month(self):
        if self.pending is None:raise ValueError('stale_battle_result')
        data,result,inputs=self.pending
        if inputs!=self.inputs() or self.app.campaign_session.to_dict()!=self.snapshot:raise ValueError('stale_battle_result')
        if not messagebox.askyesno(t('log_ui_apply'),self.output.cget('text'),parent=self):return
        self.app.campaign_session.apply_maintenance(data,result,self.snapshot)
        self.app._pending_mass_round=None
        self.app._sync_mass_fields()
        self.app._show_result(self.app.mass_result_text,[t('log_ui_applied')])
        self.destroy()
