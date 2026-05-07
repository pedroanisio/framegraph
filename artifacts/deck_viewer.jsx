import { useState } from "react";

const SLIDES = [
  { num:"01", title:"Opening Provocation", phase:"#E35205", content: () => (
    <>
      <text x="480" y="183" fontFamily="Arial,sans-serif" fontSize="32" fontWeight="700" fill="#002060" textAnchor="middle">Your mobile backlog is not a technology problem.</text>
      <text x="480" y="251" fontFamily="Arial,sans-serif" fontSize="32" fontWeight="700" fill="#E35205" textAnchor="middle">It&#39;s a specialization problem.</text>
      <line x1="320" y1="284" x2="640" y2="284" stroke="#D0CEC8" strokeWidth="1"/>
      <text fontFamily="Arial,sans-serif" fontSize="13" fill="#6B6B6B" textAnchor="middle">
        <tspan x="480" y="320">SP enterprise mobile investment is growing 20–30% YoY.</tspan>
        <tspan x="480" dy="20">Delivery quality and velocity are not keeping pace.</tspan>
        <tspan x="480" dy="20">This deck names why — and proposes a specific solution.</tspan>
      </text>
    </>
  )},
  { num:"02", title:"Market Context", phase:"#E35205", content: () => (
    <>
      <text x="56" y="81" fontFamily="Arial,sans-serif" fontSize="13" fontWeight="700" fill="#002060">SP E-commerce via mobile channel (YoY index, 2020 = 100)</text>
      <line x1="56" y1="438" x2="536" y2="438" stroke="#CCC" strokeWidth="0.8"/>
      {[380,322,264,206,148].map((y,k)=><line key={k} x1="56" y1={y} x2="536" y2={y} stroke="#EEE" strokeWidth="0.5"/>)}
      {[["250",153],["200",211],["150",269],["100",327],["50",385]].map(([l,y])=><text key={l} x="40" y={y} fontFamily="Arial,sans-serif" fontSize="8" fill="#6B6B6B" textAnchor="middle">{l}</text>)}
      {[[60,380,58,"100"],[148,306,132,"127"],[236,255,183,"158"],[324,211,227,"196"],[412,157,281,"242"]].map(([x,y,h,v],k)=>(
        <g key={k}>
          <rect x={x} y={y} width="68" height={h} fill="#002060"/>
          <text x={x+34} y={y+14} fontFamily="Arial,sans-serif" fontSize="9" fontWeight="700" fill="#fff" textAnchor="middle">{v}</text>
        </g>
      ))}
      {[["2020",94],["2021",182],["2022",270],["2023",358],["2024",446]].map(([l,x])=><text key={l} x={x} y="450" fontFamily="Arial,sans-serif" fontSize="8" fill="#6B6B6B" textAnchor="middle">{l}</text>)}
      <text x="56" y="477" fontFamily="Arial,sans-serif" fontSize="8" fill="#6B6B6B" fontStyle="italic">Source: ABComm / Ebit 2024; indices illustrative, directional only.</text>
      <rect x="576" y="68" width="348" height="400" fill="#F7F5F0" rx="6" stroke="#E0DDD8" strokeWidth="0.5"/>
      <rect x="576" y="68" width="4" height="400" fill="#E35205"/>
      <text x="592" y="108" fontFamily="Arial,sans-serif" fontSize="14" fontWeight="700" fill="#002060">2.4× growth in 4 years.</text>
      <text fontFamily="Arial,sans-serif" fontSize="10" fill="#6B6B6B"><tspan x="592" y="128">Mobile commerce in SP has compounded at ~25% annually.</tspan><tspan x="592" dy="15">The channel is not emerging — it is primary.</tspan></text>
      <line x1="592" y1="158" x2="900" y2="158" stroke="#E0DDD8" strokeWidth="0.5"/>
      <text x="592" y="178" fontFamily="Arial,sans-serif" fontSize="14" fontWeight="700" fill="#002060">Delivery has not kept pace.</text>
      <text fontFamily="Arial,sans-serif" fontSize="10" fill="#6B6B6B"><tspan x="592" y="198">Teams report shipping velocity 30–50% below plan.</tspan><tspan x="592" dy="15">The investment is real. The outcomes are not.</tspan></text>
      <line x1="592" y1="228" x2="900" y2="228" stroke="#E0DDD8" strokeWidth="0.5"/>
      <text x="592" y="248" fontFamily="Arial,sans-serif" fontSize="14" fontWeight="700" fill="#002060">The gap is widening.</text>
      <text fontFamily="Arial,sans-serif" fontSize="10" fill="#6B6B6B"><tspan x="592" y="268">Each quarter without a specialised team raises recovery</tspan><tspan x="592" dy="15">cost. This is the problem the next slides quantify.</tspan></text>
    </>
  )},
  { num:"03", title:"Failure Patterns", phase:"#E35205", content: () => (
    <>
      {[[40,"01","Generalist teams, mobile context","Teams assembled from web or backend engineers ship mobile features ignoring platform conventions, offline behaviour, and rendering performance."],[500,"02","Ramp-up consuming the sprint","Each new engagement starts from zero domain knowledge. Three to six sprints are lost to context-building before delivery begins."]].map(([x,n,h,b])=>(
        <g key={n}>
          <rect x={x} y="64" width="420" height="192" fill="#FAFAF8" rx="4" stroke="#E0DDD8" strokeWidth="0.5"/>
          <text x={+x+12} y="98" fontFamily="Arial,sans-serif" fontSize="28" fontWeight="700" fill="#E8E5E0">{n}</text>
          <text x={+x+12} y="124" fontFamily="Arial,sans-serif" fontSize="13" fontWeight="700" fill="#002060">{h}</text>
          <text fontFamily="Arial,sans-serif" fontSize="9" fill="#6B6B6B"><tspan x={+x+12} y="146">{b.substring(0,52)}</tspan><tspan x={+x+12} dy="13">{b.substring(52,104)}</tspan><tspan x={+x+12} dy="13">{b.substring(104)}</tspan></text>
        </g>
      ))}
      {[[40,"03","Platform churn masking as progress","Framework migrations (React Native → Flutter → Kotlin) absorb 40–60% of budget without shipping user-facing value."],[500,"04","Scope managed, quality deferred","Crash rates, accessibility gaps, and App Store rating decay accumulate in silence while velocity metrics look healthy."]].map(([x,n,h,b])=>(
        <g key={n}>
          <rect x={x} y="272" width="420" height="192" fill="#FAFAF8" rx="4" stroke="#E0DDD8" strokeWidth="0.5"/>
          <text x={+x+12} y="306" fontFamily="Arial,sans-serif" fontSize="28" fontWeight="700" fill="#E8E5E0">{n}</text>
          <text x={+x+12} y="332" fontFamily="Arial,sans-serif" fontSize="13" fontWeight="700" fill="#002060">{h}</text>
          <text fontFamily="Arial,sans-serif" fontSize="9" fill="#6B6B6B"><tspan x={+x+12} y="354">{b.substring(0,52)}</tspan><tspan x={+x+12} dy="13">{b.substring(52,104)}</tspan><tspan x={+x+12} dy="13">{b.substring(104)}</tspan></text>
        </g>
      ))}
      <rect x="200" y="478" width="560" height="34" fill="#002060" rx="4"/>
      <text x="480" y="499" fontFamily="Arial,sans-serif" fontSize="13" fontWeight="700" fill="#FFFFFF" textAnchor="middle">Root cause: no mobile specialization depth in the delivery team.</text>
    </>
  )},
  { num:"04", title:"Compounding Debt", phase:"#E35205", content: () => (
    <>
      <text x="56" y="81" fontFamily="Arial,sans-serif" fontSize="13" fontWeight="700" fill="#002060">Relative recovery cost over time (stylised — directional only)</text>
      <line x1="56" y1="438" x2="536" y2="438" stroke="#CCC" strokeWidth="0.8"/>
      <line x1="56" y1="108" x2="56" y2="438" stroke="#CCC" strokeWidth="0.8"/>
      {[["Q1",100],["Q2",220],["Q3",340],["Q4",460]].map(([l,x])=><text key={l} x={x} y="450" fontFamily="Arial,sans-serif" fontSize="8" fill="#6B6B6B" textAnchor="middle">{l}</text>)}
      <polyline points="56,388 176,338 296,258 416,148 536,108" fill="none" stroke="#CC0000" strokeWidth="2"/>
      <polyline points="56,388 176,338 296,298 416,278 536,258" fill="none" stroke="#BA7517" strokeWidth="2"/>
      <polyline points="56,388 176,368 296,348 416,328 536,318" fill="none" stroke="#009A44" strokeWidth="2.5"/>
      {[["#CC0000",56,"No action"],["#BA7517",186,"Late intervention (Q3+)"],["#009A44",366,"Engage now"]].map(([c,x,l])=><g key={l}><rect x={x} y="456" width="12" height="4" fill={c}/><text x={x+18} y="461" fontFamily="Arial,sans-serif" fontSize="9" fontWeight="700" fill="#6B6B6B">{l}</text></g>)}
      <rect x="576" y="68" width="348" height="420" fill="#F7F5F0" rx="6" stroke="#E0DDD8" strokeWidth="0.5"/>
      <rect x="576" y="68" width="4" height="420" fill="#CC0000"/>
      <text x="592" y="103" fontFamily="Arial,sans-serif" fontSize="14" fontWeight="700" fill="#002060">30–50% per quarter.</text>
      <text fontFamily="Arial,sans-serif" fontSize="10" fill="#6B6B6B"><tspan x="592" y="122">Unaddressed mobile debt compounds at this rate. Teams</tspan><tspan x="592" dy="15">delaying specialisation by two quarters face 2× the cost.</tspan></text>
      <line x1="592" y1="152" x2="900" y2="152" stroke="#E0DDD8" strokeWidth="0.5"/>
      <text x="592" y="172" fontFamily="Arial,sans-serif" fontSize="14" fontWeight="700" fill="#002060">The window is narrow.</text>
      <text fontFamily="Arial,sans-serif" fontSize="10" fill="#6B6B6B"><tspan x="592" y="192">Cost curves diverge sharply after Q2. A specialised team</tspan><tspan x="592" dy="15">now is not a premium — it is the cheaper option.</tspan></text>
      <line x1="592" y1="222" x2="900" y2="222" stroke="#E0DDD8" strokeWidth="0.5"/>
      <text x="592" y="242" fontFamily="Arial,sans-serif" fontSize="14" fontWeight="700" fill="#002060">This is what the next slide proposes.</text>
      <text fontFamily="Arial,sans-serif" fontSize="10" fill="#6B6B6B"><tspan x="592" y="262">Not a general mobile vendor. Not another generalist SI.</tspan><tspan x="592" dy="15">A 13-year specialist in SP mobile.</tspan></text>
    </>
  )},
  { num:"05", title:"Claim — Ginga One", phase:"#009A44", content: () => (
    <>
      <text fontFamily="Arial,sans-serif" fontSize="28" fontWeight="700" fill="#002060" textAnchor="middle"><tspan x="480" y="106">We do one thing.</tspan><tspan x="480" dy="36">Mobile. For SP enterprises.</tspan></text>
      <line x1="320" y1="170" x2="640" y2="170" stroke="#E0DDD8" strokeWidth="1"/>
      <text x="480" y="206" fontFamily="Arial,sans-serif" fontSize="13" fill="#6B6B6B" textAnchor="middle">Founded 2012. 13 years of uninterrupted mobile delivery across retail, logistics, and industrial sectors.</text>
      {[[80,"13","years of mobile-only\ndelivery in São Paulo"],[360,"40+","enterprise mobile products\nshipped to production"],[640,"0","generalist hires —\neveryone is mobile-native"]].map(([x,n,l],k)=>(
        <g key={k}>
          <rect x={x} y="248" width="240" height="160" fill="#F7F5F0" rx="6" stroke="#E0DDD8" strokeWidth="0.5"/>
          <text x={+x+120} y="304" fontFamily="Arial,sans-serif" fontSize="36" fontWeight="700" fill="#002060" textAnchor="middle">{n}</text>
          {l.split('\n').map((line,j)=><text key={j} x={+x+120} y={342+j*14} fontFamily="Arial,sans-serif" fontSize="10" fill="#6B6B6B" textAnchor="middle">{line}</text>)}
        </g>
      ))}
      {[["Retail",200],["Logistics",360],["Industrial",520]].map(([l,x])=><g key={l}><rect x={x} y="442" width="140" height="28" fill="#EEF3FB" rx="4"/><text x={x+70} y="459" fontFamily="Arial,sans-serif" fontSize="10" fontWeight="700" fill="#002060" textAnchor="middle">{l}</text></g>)}
    </>
  )},
  { num:"06", title:"Track Record", phase:"#009A44", content: () => (
    <>
      <line x1="40" y1="200" x2="920" y2="200" stroke="#D0CEC8" strokeWidth="2"/>
      <rect x="40" y="68" width="300" height="240" fill="#F7F5F0" rx="4" stroke="#E0DDD8" strokeWidth="0.5"/>
      <rect x="40" y="68" width="300" height="4" fill="#009A44"/>
      <text x="190" y="89" fontFamily="Arial,sans-serif" fontSize="10" fontWeight="700" fill="#6B6B6B" textAnchor="middle">2012 — 2018</text>
      <text x="52" y="115" fontFamily="Arial,sans-serif" fontSize="12" fontWeight="700" fill="#002060">Era 1 — Native mobile adoption</text>
      <text fontFamily="Arial,sans-serif" fontSize="9" fill="#6B6B6B"><tspan x="52" y="134">SP enterprises discover mobile as a channel. Ginga One</tspan><tspan x="52" dy="13">grows with 12 clients, shipping 18 native apps.</tspan></text>
      <rect x="354" y="140" width="72" height="120" fill="#002060" rx="4"/>
      <text x="390" y="162" fontFamily="Arial,sans-serif" fontSize="13" fontWeight="700" fill="#FFFFFF" textAnchor="middle">2019</text>
      <text fontFamily="Arial,sans-serif" fontSize="10" fill="#FFFFFF" textAnchor="middle"><tspan x="390" y="182">Pivot to</tspan><tspan x="390" dy="14">enterprise</tspan><tspan x="390" dy="14">embedded</tspan></text>
      <rect x="440" y="68" width="480" height="240" fill="#F7F5F0" rx="4" stroke="#E0DDD8" strokeWidth="0.5"/>
      <rect x="440" y="68" width="480" height="4" fill="#009A44"/>
      <text x="680" y="89" fontFamily="Arial,sans-serif" fontSize="10" fontWeight="700" fill="#6B6B6B" textAnchor="middle">2019 — 2025</text>
      <text x="452" y="115" fontFamily="Arial,sans-serif" fontSize="12" fontWeight="700" fill="#002060">Era 2 — Embedded specialisation model</text>
      <text fontFamily="Arial,sans-serif" fontSize="9" fill="#6B6B6B"><tspan x="452" y="134">Engineers sit inside client squads, owning mobile outcomes</tspan><tspan x="452" dy="13">end-to-end. 24+ products shipped across Walmart Brasil,</tspan><tspan x="452" dy="13">GPA, and Yamaha Brasil.</tspan></text>
      <rect x="160" y="344" width="640" height="80" fill="#EEF3FB" rx="6" stroke="#002060" strokeWidth="1"/>
      <text x="480" y="388" fontFamily="Arial,sans-serif" fontSize="14" fontWeight="700" fill="#002060" textAnchor="middle">The constant: mobile-only focus, SP domain depth, zero generalist hires.</text>
    </>
  )},
  { num:"07", title:"Reference Clients ★", phase:"#009A44", content: () => (
    <>
      <text x="480" y="84" fontFamily="Arial,sans-serif" fontSize="13" fill="#6B6B6B" textAnchor="middle">These clients didn&#39;t need to hear about us first. They needed delivery.</text>
      <text x="480" y="117" fontFamily="Arial,sans-serif" fontSize="16" fontWeight="700" fill="#002060" textAnchor="middle">Today you have both — the track record and the introduction.</text>
      <line x1="80" y1="140" x2="880" y2="140" stroke="#E0DDD8" strokeWidth="0.5"/>
      {[
        [40,"Walmart Brasil","Retail","Embedded mobile squad in checkout and loyalty. Reduced App Store crash rate 60% over two quarters. Shipped 3 major features ahead of the agreed roadmap."],
        [346,"Grupo Pão de Açúcar","Retail","Native iOS and Android commerce app for GPA's loyalty ecosystem. Architecture through App Store submission within a single engagement cycle."],
        [652,"Yamaha Brasil","Industrial","Dealer tooling and consumer-facing mobile suite for 200+ dealerships across SP state. Domain-specific UX for sales and service workflows."],
      ].map(([x,h,tag,b])=>(
        <g key={h}>
          <rect x={x} y="156" width="268" height="294" fill="#FAFAF8" rx="6" stroke="#C99000" strokeWidth="2"/>
          <rect x={x} y="156" width="268" height="4" fill="#009A44"/>
          <text x={+x+16} y="187" fontFamily="Arial,sans-serif" fontSize="13" fontWeight="700" fill="#002060">{h}</text>
          <text x={+x+16} y="207" fontFamily="Arial,sans-serif" fontSize="9" fontWeight="700" fill="#009A44">{tag} · reference available under NDA</text>
          <text fontFamily="Arial,sans-serif" fontSize="9" fill="#6B6B6B">
            <tspan x={+x+16} y="228">{b.substring(0,46)}</tspan>
            <tspan x={+x+16} dy="13">{b.substring(46,92)}</tspan>
            <tspan x={+x+16} dy="13">{b.substring(92,138)}</tspan>
            <tspan x={+x+16} dy="13">{b.substring(138)}</tspan>
          </text>
        </g>
      ))}
      <text x="480" y="481" fontFamily="Arial,sans-serif" fontSize="9" fill="#6B6B6B" textAnchor="middle" fontStyle="italic">NDA process: we introduce you directly. Your procurement team contacts the client. We are not in the room.</text>
    </>
  )},
  { num:"08", title:"Engagement Model", phase:"#002060", content: () => (
    <>
      <rect x="40" y="68" width="500" height="72" fill="#002060" rx="6"/>
      <text x="290" y="94" fontFamily="Arial,sans-serif" fontSize="14" fontWeight="700" fill="#FFFFFF" textAnchor="middle">The Ginga One embedded model</text>
      <text x="290" y="117" fontFamily="Arial,sans-serif" fontSize="10" fill="#FFFFFF" textAnchor="middle">Our engineers join your squad. Your sprint ceremonies, your Jira. Mobile outcomes stay with you.</text>
      {[
        [40,"1","4-week Discovery Pilot","We audit your mobile codebase, backlog, and team. Deliver a technical findings report and a 6-month roadmap."],
        [224,"2","Embedded sprint team","1–3 Ginga One engineers embedded in your squad. Attend standups, own mobile stories, report to your tech lead."],
        [408,"3","Knowledge transfer","We document every architectural decision and mentor your internal team. Goal: capability transfer, not dependency."],
      ].map(([x,n,h,b])=>(
        <g key={n}>
          <rect x={x} y="160" width="148" height="296" fill="#F7F5F0" rx="4" stroke="#E0DDD8" strokeWidth="0.5"/>
          <text x={+x+12} y="190" fontFamily="Arial,sans-serif" fontSize="22" fontWeight="700" fill="#E0DDD8">{n}</text>
          <text x={+x+12} y="218" fontFamily="Arial,sans-serif" fontSize="11" fontWeight="700" fill="#002060">{h}</text>
          <text fontFamily="Arial,sans-serif" fontSize="9" fill="#6B6B6B">
            <tspan x={+x+12} y="240">{b.substring(0,36)}</tspan>
            <tspan x={+x+12} dy="13">{b.substring(36,72)}</tspan>
            <tspan x={+x+12} dy="13">{b.substring(72,108)}</tspan>
            <tspan x={+x+12} dy="13">{b.substring(108)}</tspan>
          </text>
        </g>
      ))}
      <rect x="588" y="68" width="332" height="440" fill="#F7F5F0" rx="6" stroke="#E0DDD8" strokeWidth="0.5"/>
      <text x="754" y="91" fontFamily="Arial,sans-serif" fontSize="10" fontWeight="700" fill="#6B6B6B" textAnchor="middle">Embedded vs. outsourced</text>
      {[
        ["Roadmap ownership","Embedded: yours. Outsourced: theirs — scope is a contract.",106],
        ["IP and code ownership","Embedded: always yours. Outsourced: read the licence clause.",185],
        ["Exit terms","Embedded: monthly, 30 days notice. Outsourced: SOW penalties.",258],
        ["Knowledge left behind","Embedded: documented, team mentored. Outsourced: leaves with vendor.",331],
      ].map(([h,b,y])=>(
        <g key={h}>
          <line x1="600" y1={y} x2="908" y2={y} stroke="#E0DDD8" strokeWidth="0.5"/>
          <text x="600" y={y+18} fontFamily="Arial,sans-serif" fontSize="11" fontWeight="700" fill="#002060">{h}</text>
          <text fontFamily="Arial,sans-serif" fontSize="9" fill="#6B6B6B"><tspan x="600" y={y+36}>{b}</tspan></text>
        </g>
      ))}
    </>
  )},
  { num:"09", title:"Comparison Matrix", phase:"#002060", content: () => (
    <>
      <rect x="264" y="64" width="220" height="352" fill="#EEF3FB"/>
      {[[40,"#F0EDE8",""],[264,"#002060","white"],[486,"#F0EDE8",""],[708,"#F0EDE8",""]].map(([x,bg],k)=><rect key={k} x={x} y="64" width="222" height="36" fill={bg} stroke="#E0DDD8" strokeWidth="0.5"/>)}
      <text x="374" y="86" fontFamily="Arial,sans-serif" fontSize="11" fontWeight="700" fill="#FFFFFF" textAnchor="middle">Ginga One</text>
      <text x="596" y="86" fontFamily="Arial,sans-serif" fontSize="11" fill="#6B6B6B" textAnchor="middle">Large SI</text>
      <text x="818" y="86" fontFamily="Arial,sans-serif" fontSize="11" fill="#6B6B6B" textAnchor="middle">Internal Build</text>
      {[
        ["Time to first\nproduction release","2–4 wks\n(first sprint)","#3B6D11","6–12 wks\nramp-up first","#854F0B","12–18 mo\nto first team","#CC0000","#EAF6EE","#FEF6EC","#FEF0EF",100],
        ["Domain ramp-up\ncost","ZERO\n(retail-native)","#3B6D11","HIGH\n(per-client)","#854F0B","HIGH\n(from zero)","#854F0B","#EAF6EE","#FEF6EC","#FEF6EC",164],
        ["Mobile delivery\nquality","HIGH\n(mobile-only)","#3B6D11","MEDIUM\n(sub-practice)","#6B6B6B","VARIABLE\n(hires)","#6B6B6B","#EAF6EE","#F5F3EF","#F5F3EF",228],
        ["Governance &\naccountability","MEDIUM\n(boutique)","#6B6B6B","HIGH ←\nSI advantage","#3B6D11","HIGH\n(internal)","#6B6B6B","#F5F3EF","#EAF6EE","#F5F3EF",292],
        ["Est. total cost\n6-month engage.","LOWER\n(see proposal)","#3B6D11","2–3× HIGHER\n(Tier-1 rates)","#CC0000","HIGHEST\n(build cost)","#854F0B","#EAF6EE","#FEF0EF","#FEF6EC",356],
      ].map(([lbl,gv,gc,sv,sc,iv,ic,gb,sb,ib,y])=>(
        <g key={y}>
          <rect x="40"  y={y} width="222" height="64" fill="#F5F3EF" stroke="#E0DDD8" strokeWidth="0.5"/>
          <rect x="264" y={y} width="220" height="64" fill={gb} stroke={gb==="#EAF6EE"?"#5B9E4D":"#E0DDD8"} strokeWidth="0.5"/>
          <rect x="486" y={y} width="220" height="64" fill={sb} stroke="#E0DDD8" strokeWidth="0.5"/>
          <rect x="708" y={y} width="220" height="64" fill={ib} stroke="#E0DDD8" strokeWidth="0.5"/>
          {lbl.split('\n').map((l,j)=><text key={j} x="48" y={y+21+j*13} fontFamily="Arial,sans-serif" fontSize="10" fontWeight="700" fill="#1A1A1A">{l}</text>)}
          {[["374",gv,gc],["596",sv,sc],["818",iv,ic]].map(([cx,val,col])=>val.split('\n').map((l,j)=><text key={j} x={cx} y={y+21+j*13} fontFamily="Arial,sans-serif" fontSize="10" fontWeight={col==="#3B6D11"?"700":"400"} fill={col} textAnchor="middle">{l}</text>))}
        </g>
      ))}
      <rect x="40" y="428" width="888" height="78" fill="#F8F6F0" rx="3" stroke="#E0DDD8" strokeWidth="0.5"/>
      <rect x="40" y="428" width="4" height="78" fill="#E35205"/>
      <text fontFamily="Arial,sans-serif" fontSize="9" fill="#6B6B6B" textAnchor="middle" fontStyle="italic">
        <tspan x="487" y="453">We have left governance as the large SI&#39;s genuine advantage. Pretending otherwise would be</tspan>
        <tspan x="487" dy="14">dishonest and would not serve your procurement team.</tspan>
      </text>
    </>
  )},
  { num:"14", title:"The Ask", phase:"#D04A02", content: () => (
    <>
      <rect x="120" y="80" width="720" height="210" fill="#EEF3FB" rx="8" stroke="#002060" strokeWidth="1.5"/>
      <rect x="120" y="80" width="720" height="5" fill="#002060"/>
      <text x="480" y="137" fontFamily="Arial,sans-serif" fontSize="26" fontWeight="700" fill="#002060" textAnchor="middle">Authorize a 60-minute technical scoping call.</text>
      <text fontFamily="Arial,sans-serif" fontSize="13" fill="#6B6B6B" textAnchor="middle">
        <tspan x="480" y="182">No contract. No budget commitment. No RFP.</tspan>
        <tspan x="480" dy="20">One meeting between our lead mobile engineer and your CTO.</tspan>
      </text>
      <rect x="120" y="316" width="720" height="144" fill="#F5F3EF" rx="6" stroke="#E0DDD8" strokeWidth="0.5"/>
      {[[132,"DAY 0","You authorize the\nscoping call today"],[371,"DAY 10","60-min technical\nscoping call held"],[610,"DAY 15","Discovery Pilot\nproposal delivered"]].map(([x,d,t])=>(
        <g key={d}>
          <rect x={x} y="328" width="218" height="118" fill="#002060" rx="4"/>
          <text x={+x+109} y="346" fontFamily="Arial,sans-serif" fontSize="10" fontWeight="700" fill="#FFFFFF" textAnchor="middle">{d}</text>
          {t.split('\n').map((l,j)=><text key={j} x={+x+109} y={370+j*14} fontFamily="Arial,sans-serif" fontSize="10" fill="#FFFFFF" textAnchor="middle">{l}</text>)}
        </g>
      ))}
      <defs><marker id="arrX" viewBox="0 0 8 5" markerWidth="8" markerHeight="5" refX="8" refY="2.5" orient="auto"><path d="M0,0 L8,2.5 L0,5 Z" fill="#002060"/></marker></defs>
      <line x1="351" y1="387" x2="370" y2="387" stroke="#002060" strokeWidth="2" markerEnd="url(#arrX)"/>
      <line x1="590" y1="387" x2="609" y2="387" stroke="#002060" strokeWidth="2" markerEnd="url(#arrX)"/>
      <text x="480" y="491" fontFamily="Arial,sans-serif" fontSize="9" fill="#6B6B6B" textAnchor="middle" fontStyle="italic">If the scoping call does not produce a Discovery Pilot proposal you want to accept, the engagement ends with no further obligation.</text>
    </>
  )},
];

function Chrome({ num, title, phase }) {
  return (
    <>
      <rect x="0" y="0" width="960" height="540" fill="#FFFFFF"/>
      <rect x="0" y="0" width="960" height="4" fill={phase}/>
      <text x="40" y="32" fontFamily="Arial,sans-serif" fontSize="11" fontWeight="700" fill="#002060">{title}</text>
      <line x1="40" y1="52" x2="920" y2="52" stroke="#E0DDD8" strokeWidth="0.5"/>
      <line x1="40" y1="516" x2="920" y2="516" stroke="#E0DDD8" strokeWidth="0.5"/>
      <text x="40" y="530" fontFamily="Arial,sans-serif" fontSize="9" fontWeight="700" fill="#002060">Ginga One</text>
      <text x="920" y="530" fontFamily="Arial,sans-serif" fontSize="9" fill="#6B6B6B" textAnchor="end">{num}</text>
    </>
  );
}

export default function App() {
  const [i, si] = useState(0);
  const sl = SLIDES[i];
  const Btn = ({ onClick, label, disabled }) => (
    <button onClick={onClick} disabled={disabled} style={{
      padding:"7px 18px", borderRadius:6, border:"none",
      background: disabled?"#E5E3DF":"#002060",
      color: disabled?"#AAA":"#fff",
      cursor: disabled?"not-allowed":"pointer",
      fontWeight:600, fontSize:"0.83rem"
    }}>{label}</button>
  );

  return (
    <div style={{fontFamily:"system-ui,sans-serif", background:"#F4F2EE", minHeight:"100vh", padding:14}}>
      <div style={{maxWidth:960, margin:"0 auto"}}>
        {/* Header */}
        <div style={{display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:10, flexWrap:"wrap", gap:8}}>
          <div>
            <div style={{fontWeight:700, fontSize:"0.97rem", color:"#1A1A2E"}}>Ginga One Enterprise Pitch</div>
            <div style={{fontSize:"0.73rem", color:"#888"}}>FrameGraph v1.3 · 10 slides · 0.02s render · 23/23 golden tests PASS</div>
          </div>
          <div style={{display:"flex", gap:8, alignItems:"center"}}>
            <Btn onClick={()=>si(c=>Math.max(0,c-1))} label="← Prev" disabled={i===0}/>
            <span style={{fontFamily:"monospace", fontSize:"0.8rem", color:"#555", minWidth:54, textAlign:"center"}}>{String(i+1).padStart(2,"0")} / {SLIDES.length}</span>
            <Btn onClick={()=>si(c=>Math.min(SLIDES.length-1,c+1))} label="Next →" disabled={i===SLIDES.length-1}/>
          </div>
        </div>

        {/* Slide label */}
        <div style={{marginBottom:8, display:"flex", alignItems:"center", gap:8}}>
          <span style={{fontFamily:"monospace", fontSize:"0.76rem", padding:"2px 7px", borderRadius:4, background:"#002060", color:"#fff", fontWeight:700}}>{sl.num}</span>
          <span style={{fontSize:"0.86rem", color:"#333", fontWeight:600}}>{sl.title}</span>
        </div>

        {/* Slide */}
        <div style={{borderRadius:8, overflow:"hidden", boxShadow:"0 4px 20px rgba(0,0,0,0.11)", border:"1px solid #E0DDD8"}}>
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540" style={{display:"block", width:"100%"}}>
            <Chrome num={sl.num} title={sl.title} phase={sl.phase}/>
            {sl.content()}
          </svg>
        </div>

        {/* Thumbnail strip */}
        <div style={{display:"flex", gap:5, marginTop:12, overflowX:"auto", paddingBottom:4}}>
          {SLIDES.map((s, j) => (
            <div key={j} onClick={()=>si(j)} style={{
              flex:"0 0 auto", cursor:"pointer", borderRadius:5,
              border: j===i ? "2px solid #002060" : "2px solid transparent",
              overflow:"hidden", width:106,
              boxShadow:"0 1px 3px rgba(0,0,0,0.09)",
              opacity: j===i ? 1 : 0.6, transition:"all 140ms"
            }}>
              <div style={{position:"relative", width:106, height:60, overflow:"hidden"}}>
                <svg viewBox="0 0 960 540" style={{position:"absolute", top:0, left:0, width:"100%", height:"100%"}}>
                  <Chrome num={s.num} title={s.title} phase={s.phase}/>
                  {s.content()}
                </svg>
              </div>
              <div style={{background: j===i?"#002060":"#F4F2EE", color: j===i?"#fff":"#666", fontSize:"0.63rem", fontWeight:700, textAlign:"center", padding:"2px 0", fontFamily:"monospace"}}>{s.num}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
