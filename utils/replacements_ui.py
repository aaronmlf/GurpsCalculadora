from copy import deepcopy
import tkinter as tk
from tkinter import ttk, messagebox
from calculators.replacements import ReplacementOrder, start_replacement, advance_replacement
from utils.gui_editors import EditorWindow
from utils.editor_records import number
from utils.i18n import t


class ReplacementEditor(EditorWindow):
    def __init__(self,app,side):
        self.key='gui.mass.'+side
        if self.key not in app.campaign_session.forces:raise ValueError('invalid_replacement')
        super().__init__(app,'replacement_title')
        self.snapshot=deepcopy(app.campaign_session.to_dict())
        self.force=app.campaign_session.forces[self.key]
        self.element_ids=[e.identifier for e in self.force.elements]
        self.selection=ttk.Combobox(self.form,values=[e.name+' ['+e.identifier+']' for e in self.force.elements],state='readonly')
        self.selection.grid(row=1,column=0,columnspan=2,sticky='ew')
        self.selection.current(0)
        self.selection.bind('<<ComboboxSelected>>',lambda event:self.refresh())
        ttk.Label(self.form,text=t('replacement_help'),wraplength=720).grid(row=0,column=0,columnspan=2,sticky='w')
        self.values={k:tk.StringVar(self,value='0') for k in ('full_strength','full_cost','full_days','percent','days')}
        for row,(key,var) in enumerate(self.values.items(),2):self.entry(row,t('replacement_'+key),var)
        self.output=ttk.Label(self.form,text='',wraplength=720,justify='left')
        self.output.grid(row=7,column=0,columnspan=2,sticky='w',pady=10)
        self.action('common_calculate',self.preview)
        self.action('replacement_start',self.start)
        self.action('replacement_advance',self.advance)
        self.refresh()

    def element_id(self):return self.element_ids[self.selection.current()]

    def job(self):
        return next((j for j in self.app.campaign_session.replacement_orders
                     if j['force_id']==self.key and j['element_id']==self.element_id()),None)

    def refresh(self):
        job=self.job()
        for k,v in self.values.items():
            if k!='days':v.set(str(job[k]) if job else '0')
        self.output.configure(text=t('replacement_progress',elapsed=job['elapsed_days'],
            required=job['full_days']*job['percent']/100) if job else t('replacement_no_order'))

    def order(self):
        result=ReplacementOrder(self.key,self.element_id(),**{k:number(v.get(),float) for k,v in self.values.items() if k!='days'})
        result.validate()
        return result

    def preview(self):
        order=self.order()
        self.output.configure(text=t('replacement_quote',cost=order.cost,days=order.days,strength=order.strength))

    def start(self):
        order=self.order()
        if not messagebox.askyesno(t('replacement_start'),t('replacement_quote',cost=order.cost,days=order.days,strength=order.strength),parent=self):return
        start_replacement(self.app.campaign_session,order,self.snapshot)
        self.snapshot=deepcopy(self.app.campaign_session.to_dict())
        self.app._pending_mass_round=None
        self.refresh()

    def advance(self):
        days=number(self.values['days'].get(),float)
        if not self.job():raise ValueError('invalid_replacement')
        if not messagebox.askyesno(t('replacement_advance'),t('replacement_advance_confirm',days=days),parent=self):return
        complete=advance_replacement(self.app.campaign_session,self.key,self.element_id(),days,self.snapshot)
        self.snapshot=deepcopy(self.app.campaign_session.to_dict())
        self.app._pending_mass_round=None
        self.app._sync_mass_fields()
        self.refresh()
        if complete:self.output.configure(text=t('replacement_complete'))
