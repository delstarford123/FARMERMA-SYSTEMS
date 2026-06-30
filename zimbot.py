import os
import json
import logging
import random
from datetime import datetime, timezone, timedelta
from twilio.twiml.messaging_response import MessagingResponse
import difflib

from cachetools import TTLCache

# ==========================================
# LOGGING CONFIGURATION
# ==========================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ZIMBOT_ENGINE")

# ==========================================
# IN-MEMORY CACHE ARCHITECTURE
# ==========================================
# Protects Firebase from read spikes. Items expire after 30 minutes (1800 seconds).
market_data_cache = TTLCache(maxsize=100, ttl=1800)

# ==========================================
# ZIMBABWE MARKET HIERARCHY
# ==========================================
ZIM_REGIONS_MARKETS = {
    "Beitbridge": ["Mashavire Bulk Market"],
    "Bindura": ["Chipadze Market"],
    "Bulawayo": ["5th Avenue Market", "Shasha Market"],
    "Chegutu": ["Chegutu Market"],
    "Chimanimani": ["Nhedziwa Farmers Market", "Nhedziwa Market"],
    "Chinhoyi": ["Gadzema Market", "Makonde Horticulture Market"],
    "Chiredzi": ["Chiredzi Market"],
    "Chitungwiza": ["Guzha - Chikwanha Market", "Chikwanha Market", "Jambanja Market"],
    "Gokwe": ["Craft Centre Market", "Nembudziya - Mutora Market"],
    "Gwanda": ["Jahunda Market"],
    "Gweru": ["Mutapa Market"],
    "Harare": ["Mbare Market", "Coca Cola Market", "Cocacola Market", "BAC Market"],
    "Highfield": ["Lusaka Market"],
    "Hwange": ["Hwange Market"],
    "Kadoma": ["Rimuka Market", "City Market"],
    "Kariba": ["Nyamhunga Market"],
    "Karoi": ["Karoi Market"],
    "Kwekwe": ["Kwekwe Market"],
    "Lupane": ["Lupane Market"],
    "Marondera": ["Dombotombo Market"],
    "Masvingo": ["Garikayi Market"],
    "Mutare": ["Sakubva Market", "Chikanga Market"],
    "Norton": ["Norton Market"],
    "Nyanga": ["Nyamanda Market"],
    "Plumtree": ["Plumtree Market"],
    "Rusape": ["Rusape Market", "Evergreen Market"],
    "Ruwa": ["George Market", "Ruwa Market"],
    "Victoria Falls": ["Victoria Falls Market"],
    "Zvishavane": ["Mandava Market"]
}

SUPPORT_MESSAGE = {
    'en': "For further assistance, my human support team is ready to help you succeed.\n📧 Email: info@farmermansystems.co.ke\n💬 WhatsApp: +254 758 286236",
    'sn': "Kuti muwane rumwe rubatsiro, timu yedu iripo kukubatsirai kuti mubudirire.\n📧 Email: info@farmermansystems.co.ke\n💬 WhatsApp: +254 758 286236",
    'nd': "Ukuze uthole olunye uncedo, iqembu lethu likulungele ukukusiza ukuze uphumelele.\n📧 Email: info@farmermansystems.co.ke\n💬 WhatsApp: +254 758 286236",
    'ny': "Kuti muthandizidwe, gulu lathu la anthu lili lokonzeka kukuthandizani.\n📧 Imelo: info@farmermansystems.co.ke\n💬 WhatsApp: +254 758 286236",
    'to': "Kuti mujane lugwasyo, nkamu yesu ilibambilide kumugwasya.\n📧 Imelo: info@farmermansystems.co.ke\n💬 WhatsApp: +254 758 286236",
    'st': "Bakeng sa thuso e eketsehileng, sehlopha sa rona se ikemiselitse ho u thusa.\n📧 Email: info@farmermansystems.co.ke\n💬 WhatsApp: +254 758 286236"
}

# ==========================================
# MULTILINGUAL LOCALIZATION ENGINE (6 LANGUAGES)
# ==========================================
ZIM_TRANSLATIONS = {
    'en': {
        'welcome': "Welcome to ZIMBOT, {name} - Your Agricultural Market Intelligence Engine. I'm here to help you trade profitably.",
        'menu_prompt': "Please reply with a number to proceed:",
        'opt1': "1️⃣ Join Or Register",
        'opt2': "2️⃣ About ZIMBOT",
        'opt3': "3️⃣ Terms And Conditions",
        'opt4': "4️⃣ FAQ",
        'opt5': "5️⃣ Packages",
        'opt6': "6️⃣ Payments",
        'opt7': "7️⃣ Help Centre",
        'opt8': "8️⃣ Unsubscribe",
        'about': "*FARMERS ADVERTS AGRICULTURAL MARKET INTELLIGENCE CHATBOT*\n\nGet instant access to commodity prices, market trends, demand alerts, and expert market insights from 21 major markets across Zimbabwe including Mbare, Bulawayo, Chinhoyi, Mutare, Gweru, Masvingo, Marondera and many more.\n\n*FARMERS ADVERTS* Promoting Agribusiness through Advertising is Our Mandate 🌱📈.",
        'terms': """*Market Intelligence Chatbot*

Terms and Conditions (Ground-Verified Market Data Edition)

Effective Date: June 2026

The Farmers Adverts Market Intelligence Chatbot provides agricultural market information collected from farmers, traders, buyers, processors, markets, and other industry stakeholders. By using this chatbot, you agree to the following terms and conditions.

1. Nature of the Service

The chatbot provides:

Agricultural commodity prices

Market demand and supply information

Buyer and seller leads

Market trend analysis

Weather and production insights

Agribusiness information and educational content


Information is intended to support decision-making and improve market transparency. Similar market intelligence services emphasize that market information is provided for informational purposes and should not be considered trading or investment advice. 

2. Source of Market Information

Market information is gathered from actual market participants, including farmers, traders, wholesalers, retailers, processors, and buyers.

Information may be collected through surveys, phone calls, WhatsApp messages, market visits, and stakeholder reports.

Prices published represent prevailing market conditions at the time of collection and may change without notice.

Not every transaction in a market occurs at the same price due to differences in quality, quantity, location, transport costs, and negotiation. Market intelligence providers generally rely on market participant reports and prevailing transaction data rather than guaranteeing a single fixed market price. 


3. No Guarantee of Accuracy

While Farmers Adverts makes reasonable efforts to verify information:

We do not guarantee that all information is complete, accurate, current, or error-free.

Market conditions can change rapidly.

Users should independently verify prices and market opportunities before entering into any transaction.


This approach is consistent with common market information and data-platform disclaimers. 

4. User Responsibility

Users are solely responsible for:

Verifying prices before buying or selling.

Assessing product quality and specifications.

Negotiating transaction terms.

Conducting due diligence on buyers and sellers.


Farmers Adverts is not a party to any transaction conducted using information obtained through the chatbot. 

5. No Financial or Investment Advice

The chatbot provides market information only and does not provide:

Financial advice

Investment advice

Legal advice

Tax advice

Professional consultancy services


Users should seek professional guidance where necessary. 

6. Market Risks

Agricultural markets are affected by:

Weather conditions

Disease outbreaks

Input costs

Government policies

Exchange rate movements

Supply and demand fluctuations


Farmers Adverts cannot guarantee profits, sales, market access, or business success resulting from the use of market information. 

7. Buyer and Seller Information

Farmers Adverts may share buyer and seller opportunities for networking purposes.

Farmers Adverts does not guarantee the credibility, financial capacity, or performance of any buyer or seller.

Users are encouraged to verify all counterparties before conducting business.


8. Data Privacy

Personal information submitted through the chatbot will be used solely for service delivery, communication, and market intelligence improvement.

Farmers Adverts will not sell personal information to third parties without consent unless required by law.

Users may request correction or deletion of their personal information.


9. Intellectual Property

All reports, analyses, market summaries, and content generated by Farmers Adverts remain the property of Farmers Adverts.

Users may share information for personal use but may not reproduce, sell, or commercially distribute content without written permission.


10. Service Availability

Farmers Adverts does not guarantee uninterrupted access to the chatbot.

The service may be updated, modified, suspended, or discontinued without prior notice.


11. Limitation of Liability

Farmers Adverts shall not be liable for:

Financial losses

Trading losses

Crop or livestock losses

Missed business opportunities

Losses arising from inaccurate or outdated information

Disputes between buyers and sellers


Use of the chatbot and its information is entirely at the user's own risk. 

12. Acceptance

By using the Farmers Adverts Market Intelligence Chatbot, you confirm that:

You understand the limitations of market intelligence information.

You will independently verify critical information.

You accept these Terms and Conditions in full.


Farmers Adverts "Promoting Agribusiness Through Advertising" 🌱📢""",
        'faq': "1. *When are prices updated?* Data is updated daily from major hubs.\n2. *How accurate is the data?* We use on-ground intelligence.\n3. *How do I upgrade?* Reply with *5* for packages.",
        'pricing_intro': "Turn market information into profit with the Farmers Adverts Agricultural Market Intelligence Chatbot. 🚜 Real Prices. Real Markets. Real Decisions.\n\nSelect a professional plan to unlock intelligence access:",
        'seed': "🟢 *[A] BASIC PACKAGE ($3/mo)*\n✅ 3 times/week agricultural commodity prices from selected major markets\n✅ Basic weekly market analysis\n✅ Best market of the week\n✅ Price info for major crops\n✅ Basic farming and marketing tips\n_Ideal for smallholder farmers and traders._",
        'growth': "🟡 *[B] STANDARD PACKAGE ($5/mo)*\n✅ Updates 3 times/week on prices from 15 selected monitored markets\n✅ Market trend analysis & Price comparisons between markets\n✅ Demand and supply alerts\n✅ Best market recommendations & Profitability insights\n✅ Weather updates\n_Ideal for commercial farmers, traders and agribusinesses._",
        'harvest': "🔴 *[C] PREMIUM PACKAGE ($10/mo)*\n✅ Everything in Standard Package + Updates for 21 selected markets\n✅ AI-powered price forecasts & Supply and demand intelligence\n✅ Export market info & Wholesale buyer directory (crops/livestock)\n✅ Advanced business intelligence & Customized reports (additional fee)\n✅ 5% discount on Online Consultancy Services\n✅ 2 days advertising opportunity in Farmers Adverts WhatsApp Channel\n_Ideal for agribusinesses, investors, processors and exporters._",
        'select_plan': "Reply with *A*, *B*, or *C* to select your package.",
        'already_reg': "You are already registered, {name}. How can I assist your business today?",
        'ask_name': "Greetings. I am ZIMBOT, your professional agricultural assistant. To begin our journey to success, please provide your *Full Name*.",
        'ask_email': "Thank you, {name}. Please provide your *Email Address* to finalize your profile.",
        'ask_lang': "Which language makes you feel most at home?\n[A] English  [B] Shona  [C] Ndebele\n[D] Chewa  [E] Tonga  [F] Sotho",
        'reg_done': "Registration finalized. Welcome to the network, {name}. I'm honored to be your consultant.",
        'pay_intro': "Select a professional plan to unlock intelligence access:",
        'pay_method': "Choose payment method:\n[A] M-Pesa (STK Push)\n[B] PesaPal (Card/Online)\n[C] Paynow (EcoCash/OneMoney)",
        'lang_changed': "Language updated successfully. I'm ready to assist you.",
        'error': "I'm sorry, I'm recalibrating my feeds. Please try again in a moment.",
        'no_intel': "I want to be precise for you, but I don't have spot prices for '{query}' right now. Try a specific town, market, or product.",
        'sub_req': "I'm eager to help you, {name}, but a subscription is required for intelligence access.",
        'ambiguity': "I want to make sure I get you to the right place. Please reply with the correct letter, or type 'MENU' to go back.",
        'pivots': ["I am operating at peak efficiency. Which crop market are we analyzing today?", "Let's get down to business. Which region shall we look into?"],
        'out_of_domain': "My expertise is strictly dedicated to your agricultural success. I cannot assist with non-agricultural topics. Shall we check the market instead?"
    },
    'sn': {
        'welcome': "Tikugashirei kuZIMBOT, {name} - Injini Yenyu yeRuzivo rweMisika yeZvekurima. Ndiri pano kukubatsirai kuita purofiti.",
        'menu_prompt': "Ndapota pindura nenhamba kuti uenderere mberi:",
        'opt1': "1️⃣ Join kana Kunyoresa",
        'opt2': "2️⃣ Nezve ZIMBOT",
        'opt3': "3️⃣ Mitemo neMigariro",
        'opt4': "4️⃣ Mibvunzo Inowanzoitwa",
        'opt5': "5️⃣ Mapakeji",
        'opt6': "6️⃣ Kubhadhara",
        'opt7': "7️⃣ Rubatsiro",
        'pricing_intro': "Turn market information into profit! Sarudzai pakeji kuti muwane ruzivo rwemisika:",
        'seed': "🟢 *[A] BASIC PACKAGE ($3/mo)*\n✅ Mitengo 3 pavhiki & Kuongorora mafambiro eMisika",
        'growth': "🟡 *[B] STANDARD PACKAGE ($5/mo)*\n✅ Ruzivo kaviri pasvondo kubva kumisika 15 & Kuongorora mafambiro eMisika",
        'harvest': "🔴 *[C] PREMIUM PACKAGE ($10/mo)*\n✅ Ruzivo ruzere pamisika 21 & AI forecasts & Hurongwa hwekurima",
        'select_plan': "Pindura ne *A*, *B*, kana *C* kuti usarudze package.",
        'already_reg': "Watonyoreswa kare, {name}. Ndingakubatsira sei nhasi?",
        'ask_name': "Kwaziwai. Ndini ZIMBOT, mubatsiri wenyu wekurima. Kuti titange rwendo rwedu, ndapota ipai *Zita renyu rizere*.",
        'ask_email': "Ndatenda, {name}. Ipai *Email Address* yenyu kuti tipedze kunyoresa.",
        'ask_lang': "Ndeupi mutauro wamunoda kushandisa?\n[A] English  [B] Shona  [C] Ndebele\n[D] Chewa  [E] Tonga  [F] Sotho",
        'reg_done': "Kunyoresa kwapera. Tikugashirei, {name}. Ndiripo kukushandirai.",
        'pay_intro': "Sarudzai pakeji kuti muwane ruzivo:",
        'pay_method': "Sarudzai nzira yekubhadhara:\n[A] M-Pesa (STK Push)\n[B] PesaPal (Card/Online)\n[C] Paynow (EcoCash/OneMoney)",
        'lang_changed': "Mutauro wachinjwa. Ndiripo kukubatsirai.",
        'error': "Ndine urombo, hurongwa huri kugadziriswa. Edzai zvakare munguva pfupi.",
        'no_intel': "Handina mitengo ye '{query}' pari zvino. Edzai kutsvaga dhorobha kana musika.",
        'sub_req': "Munofanira kubhadhara kuti muwane ruzivo rwemisika.",
        'ambiguity': "Ndapota pindura nevara chairo, kana kuti nyora 'MENU' kuti udzokere kumashure.",
        'pivots': ["Ndiri kushanda nemazvo. Ndeupi musika watiri kuongorora?", "Ngatitangei basa. Inzvimbo ipi?"]
    },
    'nd': {
        'welcome': "Siyalamukela kuZIMBOT, {name} - Injini yakho Yolwazi lweMakethe yoLimo.",
        'menu_prompt': "Sicela uphendule ngenombolo ukuze uqhubeke:",
        'opt1': "1️⃣ Joyina loba Bhalisa",
        'opt2': "2️⃣ Mayelana le-ZIMBOT",
        'opt3': "3️⃣ Imithetho lemiGomo",
        'opt4': "4️⃣ Imibuzo Evame Ukubuzwa",
        'opt5': "5️⃣ Amaphakheji",
        'opt6': "6️⃣ Ukubhadhala",
        'opt7': "7️⃣ Indawo yoNcedo",
        'pricing_intro': "Turn market information into profit! Khetha iphakheji ukuze uvule ukufinyelela kokuqonda:",
        'seed': "🟢 *[A] BASIC PACKAGE ($3/mo)*\n✅ Ulwazi lwemakethe lwamasonto onke & Amathrendi",
        'growth': "🟡 *[B] STANDARD PACKAGE ($5/mo)*\n✅ Ulwazi lwamasonto amabili kuya ku-15 makethe & Ukuhlaziywa kwethrendi",
        'harvest': "🔴 *[C] PREMIUM PACKAGE ($10/mo)*\n✅ Ulwazi olugcwele kuma-21 makethe, AI forecasts & Amasu okusebenza",
        'select_plan': "Phendula ngo *A*, *B*, noma *C* ukuze ukhethe iphakheji.",
        'already_reg': "Usuvele ubhalisiwe, {name}. Ngingakusiza kanjani namuhla?",
        'ask_name': "Sawubona. Ngingu-ZIMBOT, umphathi wakho wolimo. Sicela unikeze *Igama lakho eliphelele*.",
        'ask_email': "Siyabonga, {name}. Sicela unikeze *Ikheli lakho le-Email*.",
        'ask_lang': "Uliphi ulimi oluthandayo?\n[A] English  [B] Shona  [C] Ndebele\n[D] Chewa  [E] Tonga  [F] Sotho",
        'reg_done': "Ukubhalisa sekuphothuliwe. Siyakwamukela, {name}.",
        'pay_intro': "Khetha iphakheji ukuze uvule ukufinyelela kokuqonda:",
        'pay_method': "Khetha indlela yokubhadhala:\n[A] M-Pesa (STK Push)\n[B] PesaPal (Card/Online)\n[C] Paynow (EcoCash/OneMoney)",
        'lang_changed': "Ulimi lubuyekeziwe. Sengilungele ukukusiza.",
        'error': "Isaziso: Uhlelo luyalungiswa. Sicela uzame futhi maduze.",
        'no_intel': "Angilawo amanani e- '{query}' njengamanje. Zama idolobha noma imakethe.",
        'sub_req': "Ukubhalisa kuyadingeka ukuze ufinyelele kokuqonda.",
        'ambiguity': "Sicela uphendule ngohlamvu olufanele, loba ubhale 'MENU'.",
        'pivots': ["Ngi ready. Iyiphi imakethe esiyihlaziya namuhla?"]
    },
    'ny': {
        'welcome': "Takulandirani ku ZIMBOT, {name} - Mlangizi wanu wamsika waulimi.",
        'menu_prompt': "Chonde yankhani ndi nambala kuti mupitilize:",
        'opt1': "1️⃣ Lowani kapena Lemberani",
        'opt2': "2️⃣ Za ZIMBOT",
        'opt3': "3️⃣ Migwirizano",
        'opt4': "4️⃣ Mafunso ofunsidwa",
        'opt5': "5️⃣ Mapaketi",
        'opt6': "6️⃣ Kulipira",
        'opt7': "7️⃣ Thandizo",
        'pricing_intro': "Sankhani phukusi lanu:",
        'seed': "[A] *Seed Package ($3/mo)* - Chidziwitso cha sabata",
        'growth': "[B] *Growth Package ($5/mo)* - Chidziwitso cha masabata awiri",
        'harvest': "[C] *Harvest Package ($10/mo)* - Chidziwitso chokwanira",
        'select_plan': "Yankhani ndi *A*, *B*, kapena *C*.",
        'already_reg': "Mwalembetsa kale, {name}. Ndingakuthandizeni bwanji lero?",
        'ask_name': "Moni. Ndine ZIMBOT. Chonde patsanipo *Dzina lanu lonse*.",
        'ask_email': "Zikomo, {name}. Patsanipo *Imelo* yanu.",
        'ask_lang': "Sankhani chilankhulo chanu:\n[A] English  [B] Shona  [C] Ndebele\n[D] Chewa  [E] Tonga  [F] Sotho",
        'reg_done': "Kulembetsa kwatha. Takulandirani, {name}.",
        'pay_intro': "Sankhani phukusi lanu kuti mupitilize:",
        'pay_method': "Sankhani njira yolipirira:\n[A] M-Pesa\n[B] PesaPal\n[C] Paynow",
        'lang_changed': "Chilankhulo chasinthidwa.",
        'error': "Pepani, dongosolo likukonzedwa. Yeseraninso posachedwa.",
        'no_intel': "Sindingapeze mitengo ya '{query}'. Yesani mzinda kapena msika wina.",
        'sub_req': "Mufunika kukhala wolembetsa kuti muwone izi.",
        'ambiguity': "Chonde yankhani ndi chilembo choyenera, kapena lembani 'MENU'.",
        'pivots': ["Ndili wokonzeka. Kodi tiwona msika uti lero?"]
    },
    'to': {
        'welcome': "Twamutambula ku ZIMBOT, {name} - Mugwasyi wako wamusika walimo.",
        'menu_prompt': "Kkumbila uvuwe amunamba kutegwa uzumanane:",
        'opt1': "1️⃣ Kunjila naa Kulilembesya",
        'opt2': "2️⃣ Makani aa ZIMBOT",
        'opt3': "3️⃣ Mulawo",
        'opt4': "4️⃣ Mibuzyo",
        'opt5': "5️⃣ Mapakeji",
        'opt6': "6️⃣ Kubbadala",
        'opt7': "7️⃣ Lugwasyo",
        'pricing_intro': "Sala pakeji yako:",
        'seed': "[A] *Seed Package ($3/mo)* - Makani aamvwiki",
        'growth': "[B] *Growth Package ($5/mo)* - Makani aamvwiki zyobilo",
        'harvest': "[C] *Harvest Package ($10/mo)* - Makani oonse",
        'select_plan': "Vuwa a *A*, *B*, naa *C*.",
        'already_reg': "Uli lembedwe kale, {name}. Ino ndikugwasye buti sunu?",
        'ask_name': "Ndakubuzya. Ndime ZIMBOT. Kkumbila upe *Zina lyako lyoonse*.",
        'ask_email': "Twalumba, {name}. Kkumbila upe *Imelo* yako.",
        'ask_lang': "Sala mwaambo wako:\n[A] English  [B] Shona  [C] Ndebele\n[D] Chewa  [E] Tonga  [F] Sotho",
        'reg_done': "Kulilembesya kwamana. Twamutambula, {name}.",
        'pay_intro': "Sala pakeji:",
        'pay_method': "Sala nzila yakubbadala:\n[A] M-Pesa\n[B] PesaPal\n[C] Paynow",
        'lang_changed': "Mwaambo wacincwa.",
        'error': "Mudaabe, sisitemu ilabambululwa. Langa alimwi mukuya kaciindi.",
        'no_intel': "Tandijani mitengo ya '{query}'. Langa dolobha naa musika umwi.",
        'sub_req': "Uyandika kubbadala kuti ubone makani aaya.",
        'ambiguity': "Kkumbila uvuwe amalembe aayelede, naa ulembe 'MENU'.",
        'pivots': ["Ndililibambilide. Ino musika nzi ngotulanga sunu?"]
    },
    'st': {
        'welcome': "Rea u amohela ho ZIMBOT, {name} - Motlatsi oa hau oa mmaraka oa temo.",
        'menu_prompt': "Ka kopo araba ka nomoro ho tsoela pele:",
        'opt1': "1️⃣ Kena kapa Ngolisa",
        'opt2': "2️⃣ Mabapi le ZIMBOT",
        'opt3': "3️⃣ Lipehelo",
        'opt4': "4️⃣ Lipotso",
        'opt5': "5️⃣ Liphutheloana",
        'opt6': "6️⃣ Tefo",
        'opt7': "7️⃣ Thuso",
        'pricing_intro': "Khetha sephutheloana sa hau:",
        'seed': "[A] *Seed Package ($3/mo)* - Tlhahisoleseding ea beke",
        'growth': "[B] *Growth Package ($5/mo)* - Tlhahisoleseding ea libeke tse peli",
        'harvest': "[C] *Harvest Package ($10/mo)* - Tlhahisoleseding e felletseng",
        'select_plan': "Araba ka *A*, *B*, kapa *C*.",
        'already_reg': "U se u ngolisitse, {name}. Nka u thusa joang kajeno?",
        'ask_name': "Lumela. Ke nna ZIMBOT. Ka kopo fana ka *Lebitso la hau le felletseng*.",
        'ask_email': "Kea leboha, {name}. Ka kopo fana ka *Email* ea hau.",
        'ask_lang': "Khetha puo ea hau:\n[A] English  [B] Shona  [C] Ndebele\n[D] Chewa  [E] Tonga  [F] Sotho",
        'reg_done': "Ngoliso e phethiloe. Rea u amohela, {name}.",
        'pay_intro': "Khetha sephutheloana sa hau:",
        'pay_method': "Khetha mokhoa oa ho lefa:\n[A] M-Pesa\n[B] PesaPal\n[C] Paynow",
        'lang_changed': "Puo e fetohile.",
        'error': "Tshwarelo, sistimi e nts'e e ntlafatsoa. Leka hape haufinyane.",
        'no_intel': "Ha ke fumane theko bakeng sa '{query}'. Leka toropo kapa mmaraka o mong.",
        'sub_req': "U tlameha ho ingolisa ho bona tlhahisoleseding ena.",
        'ambiguity': "Ka kopo araba ka tlhaku e nepahetseng, kapa u ngole 'MENU'.",
        'pivots': ["Ke lokile. Re sheba mmaraka ofe kajeno?"]
    }
}

# ==========================================
# MODULE: FREQUENTLY ASKED QUESTIONS (FAQ) ENGINE
# ==========================================
FAQ_MENU_ANSWERS = {
    "A1": "It is the Farmers Adverts Agricultural Market Intelligence Chatbot, an AI-powered platform providing commodity prices, market trends, demand info, and market intelligence from 21 markets across Zimbabwe.",
    "A2": "Simply send your question through WhatsApp and instantly receive market prices, trends, recommendations, and agricultural information. Turn market information into profit!",
    "A3": "21 markets including Mbare, Bulawayo, Chinhoyi, Mutare, Gweru, Masvingo, Marondera, Bindura, Kadoma, Kwekwe, and others. We cover Livestock and crops.",
    "A4": "Prices are updated regularly based on market data collected from monitored markets.",
    "A5": "The chatbot uses data collected from monitored markets and reliable sources. Prices may vary due to market conditions and timing.",
    "B1": "Yes. The chatbot can compare commodity prices across multiple markets to help you identify the best place to sell or buy. Based on available data, the chatbot suggests markets offering the best prices.",
    "B2": "Yes. Standard and Premium subscribers receive market trend analysis and price movement reports. Standard and Premium packages provide access to historical price information.",
    "B3": "Yes. Standard and Premium subscribers receive market alerts and opportunities. Premium subscribers receive market forecasts and price outlook reports.",
    "B4": "Yes. Weather updates are available in selected packages. The chatbot can provide basic agronomic information and farming tips.",
    "C1": "Basic Package, Standard Package, and Premium Package. Subscription fees will be communicated by Farmers Adverts upon launch.",
    "C2": "You can subscribe through Farmers Adverts using the provided payment and registration channels. Yes. Subscribers can cancel according to the terms and conditions.",
    "C3": "Yes. The chatbot is available 24 hours a day, 7 days a week. Designed for farmers, traders, buyers, agro-dealers, processors, and agribusinesses."
}

FAQ_RAW_ANSWERS = {
    "what is the chatbot": FAQ_MENU_ANSWERS["A1"],
    "how does it work": FAQ_MENU_ANSWERS["A2"],
    "which markets are covered": "21 markets including Mbare, Bulawayo, Chinhoyi, Mutare, Gweru, Masvingo, Marondera, Bindura, Kadoma, Kwekwe, and others.",
    "what commodities are covered": "Livestock and crops.",
    "how often are prices updated": FAQ_MENU_ANSWERS["A4"],
    "how accurate is the information": FAQ_MENU_ANSWERS["A5"],
    "compare prices": "Yes. The chatbot can compare commodity prices across multiple markets to help you identify the best place to sell or buy.",
    "best market to sell": "Yes. Based on available data, the chatbot suggests markets offering the best prices.",
    "market trends": "Yes. Standard and Premium subscribers receive market trend analysis and price movement reports.",
    "historical prices": "Yes. Standard and Premium packages provide access to historical price information.",
    "weather information": "Yes. Weather updates are available in selected packages.",
    "farming questions": "Yes. The chatbot can provide basic agronomic information and farming tips.",
    "market alerts": "Yes. Standard and Premium subscribers receive market alerts and opportunities.",
    "predict future prices": "Yes. Premium subscribers receive market forecasts and price outlook reports.",
    "available packages": "Basic Package, Standard Package, and Premium Package.",
    "how much does it cost": "Subscription fees will be communicated by Farmers Adverts upon launch.",
    "how do i subscribe": "You can subscribe through Farmers Adverts using the provided payment and registration channels.",
    "can i cancel": "Yes. Subscribers can cancel according to the terms and conditions.",
    "available 24/7": "Yes. The chatbot is available 24 hours a day, 7 days a week.",
    "who can use it": "Designed for farmers, traders, buyers, agro-dealers, processors, and agribusinesses.",
    "who benefits": "Farmers, Traders, Buyers, Agro-dealers, Farmer Organisations, Processors, Exporters, and Agribusiness Investors."
}

def get_nl_faq_answer(msg_low):
    for q, ans in FAQ_RAW_ANSWERS.items():
        if q in msg_low or all(w in msg_low for w in q.split() if len(w) > 4):
            return f"{ans}"
    return None

def handle_faq(msg_clean, phone, session_data, rtdb):
    step = session_data.get('step')
    
    if step == 'category_selection':
        if msg_clean == 'A':
            set_session_state(rtdb, phone, 'faq', step='view_category', category='A')
            return "Here are the General Questions. Reply with a number to see the answer:\n[A1] What is this chatbot?\n[A2] How does it work?\n[A3] Which markets and commodities are covered?\n[A4] How often are prices updated?\n[A5] How accurate is the data?\nReply with MENU to go back."
        elif msg_clean == 'B':
            set_session_state(rtdb, phone, 'faq', step='view_category', category='B')
            return "Here are our Intelligence Capabilities. Reply with a number to see the answer:\n[B1] Can I compare prices or find the best market to sell?\n[B2] Do you provide market trends and historical prices?\n[B3] Will I receive market alerts or future predictions?\n[B4] Do you provide weather info and farming tips?\nReply with MENU to go back."
        elif msg_clean == 'C':
            set_session_state(rtdb, phone, 'faq', step='view_category', category='C')
            return "Here is information on Subscriptions. Reply with a number to see the answer:\n[C1] What packages are available and how much do they cost?\n[C2] How do I subscribe or cancel?\n[C3] Is the bot 24/7? Who can use it?\nReply with MENU to go back."
        else:
            nl_ans = get_nl_faq_answer(msg_clean.lower())
            if nl_ans:
                return nl_ans
            return "🌾 *FREQUENTLY ASKED QUESTIONS* To help you find what you need quickly, please select a category below by replying with A, B, or C:\n\n[A] General Information & Markets Covered\n[B] Bot Capabilities & Market Intelligence\n[C] Subscriptions, Pricing & Access\n\nReply with a letter, or simply type your specific question right now!"
            
    elif step == 'view_category':
        cat = session_data.get('category')
        if msg_clean.startswith(cat) and msg_clean in FAQ_MENU_ANSWERS:
            ans = FAQ_MENU_ANSWERS[msg_clean]
            cat_names = {'A': 'general', 'B': 'capability', 'C': 'subscription'}
            return f"{ans}\n\nReply with '{cat}' for more {cat_names.get(cat, 'category')} questions, or 'MENU' for the main screen."
        elif msg_clean == cat:
            if msg_clean == 'A': return "Here are the General Questions. Reply with a number to see the answer:\n[A1] What is this chatbot?\n[A2] How does it work?\n[A3] Which markets and commodities are covered?\n[A4] How often are prices updated?\n[A5] How accurate is the data?\nReply with MENU to go back."
            elif msg_clean == 'B': return "Here are our Intelligence Capabilities. Reply with a number to see the answer:\n[B1] Can I compare prices or find the best market to sell?\n[B2] Do you provide market trends and historical prices?\n[B3] Will I receive market alerts or future predictions?\n[B4] Do you provide weather info and farming tips?\nReply with MENU to go back."
            elif msg_clean == 'C': return "Here is information on Subscriptions. Reply with a number to see the answer:\n[C1] What packages are available and how much do they cost?\n[C2] How do I subscribe or cancel?\n[C3] Is the bot 24/7? Who can use it?\nReply with MENU to go back."
        else:
            nl_ans = get_nl_faq_answer(msg_clean.lower())
            if nl_ans: return nl_ans
            return f"Please reply with a valid option (e.g., {cat}1), reply with '{cat}' to view questions again, or 'MENU' to exit."

    return "I couldn't process that. Please reply with MENU to go back."

# ==========================================
# CORE UTILITIES
# ==========================================
def get_zim_text(key, lang='en', **kwargs):
    """Safely retrieves translated text with English fallback."""
    try:
        lang_dict = ZIM_TRANSLATIONS.get(lang, ZIM_TRANSLATIONS['en'])
        text_template = lang_dict.get(key, ZIM_TRANSLATIONS['en'].get(key, ''))
        if 'name' not in kwargs:
            kwargs['name'] = 'Valued Farmer'
        return text_template.format(**kwargs)
    except Exception as e:
        logger.error(f"Translation Error for key '{key}': {e}")
        return ""

def get_zimbot_pesapal_ipn_id(token, host_url, rtdb):
    """Retrieves or registers the IPN ID dynamically, caching it in Firebase."""
    from pesapal_helper import register_pesapal_ipn
    ipn_cache_key = host_url.replace('.', '_').replace('/', '_').replace(':', '_')
    try:
        cached = rtdb.reference(f'pesapal_ipns/{ipn_cache_key}').get()
        if cached and isinstance(cached, dict) and 'ipn_id' in cached:
            return cached['ipn_id']
    except Exception as ex:
        logger.error(f"Error accessing firebase IPN cache: {ex}")
        
    # Register new IPN URL
    ipn_endpoint = f"{host_url}/pesapal-ipn"
    res = register_pesapal_ipn(token, ipn_endpoint)
    if res and isinstance(res, dict):
        ipn_id = res.get('ipn_id')
        if ipn_id:
            try:
                rtdb.reference(f'pesapal_ipns/{ipn_cache_key}').set({
                    'ipn_id': ipn_id,
                    'url': ipn_endpoint,
                    'registered_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
            except Exception as ex:
                logger.error(f"Error caching IPN: {ex}")
            return ipn_id
    return None

def get_zim_intent(msg):
    """Detects Natural Language Intents for Global Routing."""
    msg = msg.lower().strip()
    
    # Normalize keycap emojis like 3️⃣ -> 3
    for i in range(1, 8):
        msg = msg.replace(f"{i}️⃣", str(i))
    
    # Extract exact words to avoid substring collisions (e.g. "Chinhoyi" triggering "hi")
    import re
    words = set(re.findall(r'\b\w+\b', msg))
    
    greetings = {'menu', 'home', 'cancel', 'reset', 'menyu', 'mwanzo', 'chinja', 'hello', 'hi', 'hey', 'greetings', 'mhoro', 'sawubona', 'moni', 'lumela'}
    if any(w in greetings for w in words):
        return 'menu'
        
    if any(w in {'language', 'mutauro', 'ulimi'} for w in words):
        return 'change_lang'

    if any(w in {'unsubscribe', 'kurega', 'stop', 'exit', 'delete profile', 'kudzimba'} for w in words):
        return 'unsubscribe'
    
    # Check if msg is exactly a number 1-7 or starts with a digit 1-7
    msg_clean = msg.replace('.', '').replace(')', '').replace('-', '').strip()
    if msg_clean in ['1', '2', '3', '4', '5', '6', '7']:
        return msg_clean
        
    for d in ['1', '2', '3', '4', '5', '6', '7']:
        if msg_clean.startswith(d) and (len(msg_clean) == 1 or not msg_clean[1].isdigit()):
            return d
            
    mappings = {
        '1': ['register', 'join', 'kunyoresa', 'bhalisa', 'nyoresa', 'ngolisa', 'lemberani'],
        '2': ['about', 'nezvedu', 'mayelana', 'info', 'ndiyani'],
        '3': ['terms', 'mitemo', 'imithetho', 'conditions', 'lipehelo', 'migwirizano'],
        '4': ['faq', 'mibvunzo', 'imibuzo', 'help questions', 'lipotso', 'how the bot works'],
        '5': ['package', 'plan', 'pakeji', 'phakheji', 'tier', 'mapaketi'],
        '6': ['pay', 'mari', 'bhadhara', 'ukubhadhala', 'kulipira', 'tefo'],
        '7': ['help', 'rubatsiro', 'uncedo', 'support', 'human', 'thuso']
    }
    for opt, keywords in mappings.items():
        if any(k in msg for k in keywords):
            return opt
    return None

# ==========================================
# FIREBASE SESSION MANAGEMENT (STATE)
# ==========================================
def get_session_state(rtdb, phone):
    """Fetches user flow state from Firebase."""
    try:
        uid = f"wa_{phone}"
        state_data = rtdb.reference(f'users/{uid}/session_state').get()
        return state_data if state_data else None
    except Exception as e:
        logger.error(f"Firebase Session Fetch Error: {e}")
        return None

def set_session_state(rtdb, phone, state, **kwargs):
    """Sets user flow state in Firebase."""
    try:
        uid = f"wa_{phone}"
        mapping = {'current_state': state}
        mapping.update(kwargs)
        rtdb.reference(f'users/{uid}/session_state').set(mapping)
    except Exception as e:
        logger.error(f"Firebase Session Set Error: {e}")

def clear_session_state(rtdb, phone):
    """Wipes the user's active flow session from Firebase."""
    try:
        uid = f"wa_{phone}"
        rtdb.reference(f'users/{uid}/session_state').delete()
    except Exception as e:
        logger.error(f"Firebase Session Clear Error: {e}")

# ==========================================
# MODULAR HANDLERS
# ==========================================
def handle_registration(msg_clean, phone, session_data, rtdb, lang, user_uid):
    """Handles the multi-step profile creation flow."""
    step = session_data.get('step')
    
    if step == 'ask_name':
        full_name = msg_clean.title()
        set_session_state(rtdb, phone, 'registration', step='ask_lang', full_name=full_name)
        return get_zim_text('ask_lang', 'en', name=full_name)
        
    elif step == 'ask_lang':
        lang_map = {'A': 'en', 'B': 'sn', 'C': 'nd', 'D': 'ny', 'E': 'to', 'F': 'st'}
        if msg_clean in lang_map:
            chosen_lang = lang_map[msg_clean]
            set_session_state(rtdb, phone, 'registration', step='ask_email', full_name=session_data.get('full_name'), language=chosen_lang)
            return get_zim_text('ask_email', chosen_lang, name=session_data.get('full_name'))
        return get_zim_text('ambiguity', lang)
        
    elif step == 'ask_email':
        email = msg_clean.lower()
        if '@' not in email:
            return "I want to ensure your profile is perfect. Please provide a valid email address."
        
        u_lang = session_data.get('language', 'en')
        full_name = session_data.get('full_name', 'Valued Farmer')
        
        # Save source-of-truth to Firebase
        rtdb.reference(f'users/{user_uid}').set({
            'uid': user_uid, 'full_name': full_name, 'email': email, 'phone': phone,
            'role': 'buyer', 'subscription_tier': 'free', 'subscription_status': 'inactive',
            'language': u_lang, 'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        clear_session_state(rtdb, phone)
        tip_text = "💡 *Tip:* You can now ask me market questions directly!\nFor example, type: _'What is the price of maize in Harare?'_ or _'Weather in Mutare'_."
        return get_zim_text('reg_done', u_lang, name=full_name) + "\n\n" + get_zim_text('welcome', u_lang, name=full_name) + "\n\n" + tip_text
        
    return get_zim_text('error', lang)

def handle_payments(msg_clean, phone, session_data, rtdb, lang, system_pricing, initiate_stk_push, user_uid, user_name):
    """Handles package selection and gateway routing."""
    step = session_data.get('step')
    
    paynow_links = {
        'basic': "https://www.paynow.co.zw/Payment/Link/?q=c2VhcmNoPUFtZWRpYWZyaWNhJTQwZ21haWwuY29tJmFtb3VudD0zLjAwJnJlZmVyZW5jZT16aW1ib3QyMDI2a2VuYm90Jmw9MQ%3d%3d",
        'standard': "https://www.paynow.co.zw/Payment/Link/?q=c2VhcmNoPUFtZWRpYWZyaWNhJTQwZ21haWwuY29tJmFtb3VudD01LjAwJnJlZmVyZW5jZT16aW1ib3QyMDI2a2VuYm90Jmw9MQ%3d%3d",
        'premium': "https://www.paynow.co.zw/Payment/Link/?q=c2VhcmNoPUFtZWRpYWZyaWNhJTQwZ21haWwuY29tJmFtb3VudD0xMC4wMCZyZWZlcmVuY2U9emltYm90MjAyNmtlbmJvdCZsPTE%3d"
    }

    if step == 'select_package':
        plan_map = {'A': 'basic', 'B': 'standard', 'C': 'premium'}
        if msg_clean in plan_map:
            selected_plan = plan_map[msg_clean]
            
            # Save the selected plan to session and ask for payment method
            set_session_state(rtdb, phone, 'payments', step='select_payment_method', selected_plan=selected_plan)
            return get_zim_text('pay_method', lang)
            
        return get_zim_text('ambiguity', lang)
        
    elif step == 'select_payment_method':
        selected_plan = session_data.get('selected_plan')
        method_map = {'A': 'mpesa', 'B': 'pesapal', 'C': 'paynow'}
        
        if msg_clean in method_map:
            chosen_method = method_map[msg_clean]
            plan_details = system_pricing.get(selected_plan, {'name': 'Package', 'kes': 450, 'usd': 3.0})
            
            if chosen_method == 'mpesa':
                set_session_state(rtdb, phone, 'payments', step='ask_mpesa_phone', selected_plan=selected_plan)
                return "Please reply with your M-Pesa phone number in the format *2547XXXXXXXX*:"
                
            elif chosen_method == 'pesapal':
                try:
                    # Dynamically obtain token and register IPN
                    from flask import request
                    import time
                    from pesapal_helper import get_pesapal_token, submit_pesapal_order
                    
                    host_url = request.host_url.rstrip('/')
                    callback_url = f"{host_url}/pesapal-callback"
                    
                    token = get_pesapal_token()
                    if not token:
                        return "Failed to authenticate with PesaPal API. Please try again later."
                        
                    # Get IPN id
                    ipn_id = get_zimbot_pesapal_ipn_id(token, host_url, rtdb)
                    if not ipn_id:
                        return "Failed to register PesaPal IPN webhook. Please try again later."
                        
                    # Prep user details
                    user_profile = rtdb.reference(f'users/{user_uid}').get() or {}
                    email = user_profile.get('email', 'customer@example.com')
                    phone_num = user_profile.get('phone', phone)
                    full_name = user_profile.get('full_name', user_name)
                    
                    names = full_name.split(' ', 1)
                    first_name = names[0]
                    last_name = names[1] if len(names) > 1 else 'Farmer'
                    
                    merchant_ref = f"PESA_{user_uid[-6:]}_{int(time.time())}"
                    amount = float(plan_details['kes'])
                    currency = "KES"
                    
                    # Log pending transaction in Firebase
                    rtdb.reference(f'pending_transactions/{merchant_ref}').set({
                        'user_id': user_uid,
                        'amount': amount,
                        'plan_id': selected_plan,
                        'status': 'awaiting_payment',
                        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                    
                    # Submit the order to PesaPal
                    order_res = submit_pesapal_order(
                        token=token,
                        order_reference=merchant_ref,
                        amount=amount,
                        currency=currency,
                        description=f"Zimbot: {plan_details['name']}",
                        callback_url=callback_url,
                        ipn_id=ipn_id,
                        email=email,
                        phone=phone_num,
                        first_name=first_name,
                        last_name=last_name
                    )
                    
                    if order_res and isinstance(order_res, dict) and order_res.get('redirect_url'):
                        url = order_res['redirect_url']
                        clear_session_state(rtdb, phone)
                        return f"Perfect. Please click the link below to pay securely via PesaPal:\n\n{url}\n\nOnce completed, your subscription will be activated automatically."
                    else:
                        return f"Failed to initiate transaction with PesaPal. Details: {order_res}"
                except Exception as e:
                    logger.error(f"Pesapal Zimbot Error: {e}", exc_info=True)
                    return f"Error initiating PesaPal session. Please try again later."
                    
            elif chosen_method == 'paynow':
                # Return static Paynow link and auto-upgrade user
                url = paynow_links[selected_plan]
                
                from datetime import datetime, timedelta, timezone
                eat_tz = timezone(timedelta(hours=3))
                expiry_date = (datetime.now(eat_tz) + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
                
                rtdb.reference(f'users/{user_uid}').update({
                    'subscription_tier': selected_plan,
                    'subscription_status': 'active',
                    'subscription_expiry': expiry_date
                })
                
                clear_session_state(rtdb, phone)
                return f"Perfect. Please click the link below to pay securely via Paynow:\n\n{url}\n\nYour intelligence access for the {selected_plan.title()} package has been activated and will last for 1 month!"
                
        return get_zim_text('ambiguity', lang)
        
    elif step == 'ask_mpesa_phone':
        selected_plan = session_data.get('selected_plan')
        # Validate phone number
        mpesa_phone = msg_clean.replace('+', '').strip()
        if not mpesa_phone.isdigit() or len(mpesa_phone) < 9:
            return "Please enter a valid M-Pesa phone number in format 2547XXXXXXXX:"
            
        plan_details = system_pricing.get(selected_plan, {'name': 'Package', 'kes': 450})
        amount = int(float(plan_details['kes']))
        
        try:
            res = initiate_stk_push(mpesa_phone, amount)
            if res and res.get('ResponseCode') == '0':
                checkout_id = res.get("CheckoutRequestID")
                # Store pending transaction for callback matching
                rtdb.reference(f'pending_transactions/{checkout_id}').set({
                    'user_id': user_uid, 
                    'amount': amount, 
                    'plan_id': selected_plan, 
                    'status': 'awaiting_payment',
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
                clear_session_state(rtdb, phone)
                return f"M-Pesa STK push initiated successfully to {mpesa_phone}. Please enter your M-Pesa PIN on your phone to complete payment of KES {amount}."
            else:
                error_msg = res.get('errorMessage', 'M-Pesa service is currently unavailable.') if res else 'No response from Safaricom.'
                return f"M-Pesa STK Push failed: {error_msg}. Please try again or select another payment method."
        except Exception as e:
            logger.error(f"Zimbot M-Pesa STK Error: {e}", exc_info=True)
            return "Failed to connect to Safaricom gateway. Please try again later or choose another payment method."
            
    return get_zim_text('error', lang)

def process_intelligence_query(msg_low, lang, rtdb, persona_intro):
    """
    Core NLP Search Engine with TTLCache (Thundering Herd Protection).
    """
    # 1. Parse Entities
    det_reg = next((r for r in ZIM_REGIONS_MARKETS.keys() if r.lower() in msg_low), None)
    det_mkt = next((m for markets in ZIM_REGIONS_MARKETS.values() for m in markets if m.lower() in msg_low), None)
    
    # 2. Local Cache Check
    cache_key = f"intel:{det_reg or 'any'}:{det_mkt or 'any'}:{msg_low.replace(' ', '_')}"
    
    if cache_key in market_data_cache:
        logger.info(f"CACHE HIT: Serving intelligence for {cache_key}")
        return market_data_cache[cache_key]

    logger.info(f"CACHE MISS: Generating intelligence for {cache_key}")
    
    # 3. Database Fetch & Heavy Processing
    market_ref = rtdb.reference('market_data')
    zim_items = [v for v in (market_ref.get() or {}).values() if v.get('country') == 'Zimbabwe']
    
    # Helper: Fuzzy NLP Token Matching
    def fuzzy_match(target_list, text, cutoff=0.8):
        text_lower = text.lower()
        tokens = text_lower.split()
        for t in target_list:
            if t.lower() in text_lower: return t
            if difflib.get_close_matches(t.lower(), tokens, n=1, cutoff=cutoff): return t
        return None

    # Enhanced Accuracy Parsing via Fuzzy NLP
    det_reg = fuzzy_match(list(ZIM_REGIONS_MARKETS.keys()), msg_low)
    all_markets = [m for markets in ZIM_REGIONS_MARKETS.values() for m in markets]
    det_mkt = fuzzy_match(all_markets, msg_low)
    all_comms = list(set(v['commodity'] for v in zim_items if 'commodity' in v))
    det_comm = fuzzy_match(all_comms, msg_low)
    
    intel = {"type": "void", "data": None}
    if det_reg and not det_mkt and not det_comm:
        data = [i for i in zim_items if i.get('region') == det_reg]
        if data: intel = {"type": "region_report", "data": data, "region": det_reg}
    elif det_mkt and not det_comm:
        data = [i for i in zim_items if i.get('market') == det_mkt]
        if data: intel = {"type": "market_report", "data": data, "market": det_mkt}
    elif det_comm and not det_reg and not det_mkt:
        data = [i for i in zim_items if i.get('commodity') == det_comm]
        if data: intel = {"type": "commodity_report", "data": data, "commodity": det_comm}
    elif det_comm and (det_mkt or det_reg):
        match = next((i for i in zim_items if i['commodity'] == det_comm and (i.get('market') == det_mkt or i.get('region') == det_reg)), None)
        if match: intel = {"type": "exact", "data": match}

    # 4. Format Output
    LBL = {
        'en': {'reg_rep': 'Regional Intelligence', 'mkt_rep': 'Market Intelligence', 'comm_rep': 'Commodity Intelligence', 'comm': 'Commodity', 'mkt': 'Market', 'town': 'Town', 'price': 'Price', 'trend': 'Trend', 'act': 'Consultant Advice', 'rise': 'Rising ▲', 'drop': 'Dropping ▼', 'stab': 'Stable ▬'},
        'sn': {'reg_rep': 'Ruzivo rweDunhu', 'mkt_rep': 'Ruzivo rweMusika', 'comm_rep': 'Ruzivo rweMbesa', 'comm': 'Mbesa', 'mkt': 'Musika', 'town': 'Dhorobha', 'price': 'Mutengo', 'trend': 'Mafambiro', 'act': 'Mazano eNyanzvi', 'rise': 'Kukwira ▲', 'drop': 'Kuderera ▼', 'stab': 'Kwakamira ▬'},
        'nd': {'reg_rep': 'Ulwazi lwesiFunda', 'mkt_rep': 'Ulwazi lweMakethe', 'comm_rep': 'Ulwazi lweSilo', 'comm': 'Isilo', 'mkt': 'Imakethe', 'town': 'Idolobha', 'price': 'Intengo', 'trend': 'Amathrendi', 'act': 'Iseluleko Somphathi', 'rise': 'Kuyakhwela ▲', 'drop': 'Kuyawa ▼', 'stab': 'Kumile ▬'},
        'ny': {'reg_rep': 'Nzeru Zamdera', 'mkt_rep': 'Nzeru Zamsika', 'comm_rep': 'Nzeru Zinthu', 'comm': 'Chinthu', 'mkt': 'Msika', 'town': 'Mzinda', 'price': 'Mtengo', 'trend': 'Zochitika', 'act': 'Upangiri', 'rise': 'Kukwera ▲', 'drop': 'Kutsika ▼', 'stab': 'Kukhazikika ▬'},
        'to': {'reg_rep': 'Makani Aacisi', 'mkt_rep': 'Makani Aamusika', 'comm_rep': 'Makani Aazintu', 'comm': 'Cintu', 'mkt': 'Musika', 'town': 'Dolobha', 'price': 'Muulo', 'trend': 'Zicitika', 'act': 'Lulayo', 'rise': 'Kuya atala ▲', 'drop': 'Kuya ansi ▼', 'stab': 'Kutacinca ▬'},
        'st': {'reg_rep': 'Tlhahisoleseding ya Setereke', 'mkt_rep': 'Tlhahisoleseding ya Mmaraka', 'comm_rep': 'Tlhahisoleseding ya Sehlahiswa', 'comm': 'Sehlahiswa', 'mkt': 'Mmaraka', 'town': 'Toropo', 'price': 'Theko', 'trend': 'Mokhoa', 'act': 'Keletso', 'rise': 'Ea Nyoloha ▲', 'drop': 'Ea Theoha ▼', 'stab': 'E Tsitsitse ▬'}
    }.get(lang, {'reg_rep': 'Regional Intelligence', 'mkt_rep': 'Market Intelligence', 'comm_rep': 'Commodity Intelligence', 'comm': 'Commodity', 'mkt': 'Market', 'town': 'Town', 'price': 'Price', 'trend': 'Trend', 'act': 'Consultant Advice', 'rise': 'Rising ▲', 'drop': 'Dropping ▼', 'stab': 'Stable ▬'})

    reply_text = ""
    if intel['type'] == "region_report":
        reply_text = f"{persona_intro}📍 *{LBL['reg_rep']}: {intel['region']}*\n\nHere are the markets covered in this region and their top commodities:\n\n"
        m_f = {}
        for i in intel['data']: m_f.setdefault(i.get('market', 'General Hub'), []).append(i)
        
        for m, items in m_f.items():
            reply_text += f"🏪 *{m}:*\n"
            # Limit to top 3 to keep it clean and organized bit by bit
            items = sorted(items, key=lambda x: x.get('trend', 'stable'), reverse=True)[:3]
            for i in items:
                tr = "▲" if i.get('trend')=='up' else "▼" if i.get('trend')=='down' else "▬"
                reply_text += f"   • {i['commodity']}: {i['currency']} {i['price']} {tr}\n"
            reply_text += "\n"
        
        example_mkt = list(m_f.keys())[0] if m_f else 'Mbare Market'
        reply_text += f"💡 *Want more details?*\nType a specific market (e.g., 'Prices in {example_mkt}') or a specific crop (e.g., 'Maize in {intel['region']}')."
    
    elif intel['type'] == "market_report":
        reply_text = f"{persona_intro}🎯 *{LBL['mkt_rep']}: {intel['market']}*\n\nHere are the commodity prices for {intel['market']}:\n\n"
        for i in intel['data'][:15]:
            tr = "▲" if i.get('trend')=='up' else "▼" if i.get('trend')=='down' else "▬"
            reply_text += f"• *{i['commodity']}:* {i['currency']} {i['price']} {tr}\n"
        reply_text += f"\n💡 *Want specific details?* Type a crop name (e.g., 'Tomatoes in {intel['market']}')."
        
    elif intel['type'] == "commodity_report":
        reply_text = f"{persona_intro}📦 *{LBL['comm_rep']}: {intel['commodity']}*\n\nNational spot prices across Zimbabwe:\n\n"
        for i in intel['data']:
            tr = "▲" if i.get('trend')=='up' else "▼" if i.get('trend')=='down' else "▬"
            reply_text += f"• *{i['market']}* ({i['region']}): {i['currency']} {i['price']} {tr}\n"
        reply_text += f"\n📈 *{LBL['act']}:* The national trend is active. I suggest moving stock to hubs with 'Rising ▲' indicators."
        
    elif intel['data']:
        data = intel['data']; trend = data.get('trend', 'stable')
        price_val = float(data['price'].replace(',', '')) if isinstance(data['price'], str) else float(data['price'])
        
        reply_text = f"{persona_intro}🎯 *Targeted Intelligence: {data['commodity']}*\n\n"
        reply_text += f"📦 *{LBL['comm']}:* {data['commodity']}\n🏪 *{LBL['mkt']}:* {data.get('market','Hub')}\n📍 *{LBL['town']}:* {data.get('region','Zim')}\n"
        reply_text += f"💰 *{LBL['price']}:* {data.get('currency')} {data['price']} per {data.get('unit','unit')}\n"
        reply_text += f"📊 *{LBL['trend']}:* {LBL['rise'] if trend=='up' else LBL['drop'] if trend=='down' else LBL['stab']}\n\n"
        
        # PREDICTIVE AI FORECASTING (New Feature)
        try:
            from ai_logic.ai_engine import generate_price_forecast
            from datetime import datetime, timedelta
            # Generate synthetic history to power the AI engine since Firebase only holds spot price
            modifier = 0.95 if trend == 'up' else 1.05 if trend == 'down' else 1.0
            history = [
                {'date': (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d'), 'price': price_val * modifier},
                {'date': (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'), 'price': price_val * ((modifier + 1.0)/2)},
                {'date': datetime.now().strftime('%Y-%m-%d'), 'price': price_val}
            ]
            # Since AI engine needs at least 5 points, pad it
            history = [{'date': (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d'), 'price': price_val * (modifier ** (i/5))} for i in range(5, 0, -1)]
            
            forecast = generate_price_forecast(history, days_to_predict=3)
            if "predicted_prices" in forecast:
                predicted_end = forecast["predicted_prices"][-1]
                reply_text += f"🔮 *AI 3-Day Forecast:* Predicted to reach {data.get('currency')} {predicted_end:,.2f}.\n\n"
        except Exception as e:
            logger.warning(f"AI Forecast failed: {e}")
            
        advice = "Prices are rising! It's a great time to sell in batches." if trend=='up' else "Market glut detected. I suggest holding your stock if possible." if trend=='down' else "Market is stable. Proceed with your standard supply contracts."
        reply_text += f"⚡ *{LBL['act']}:* {advice}"
    else: 
        reply_text = get_zim_text('no_intel', lang, query=msg_low)

    # 5. Save to TTLCache (TTL is handled automatically by cachetools)
    if intel['type'] != "void":
        market_data_cache[cache_key] = reply_text

    return reply_text

def process_weather_query(msg_low, lang, rtdb, persona_intro):
    """Parses region from query and fetches active climate alerts."""
    import difflib
    
    # 1. Parse Region
    regions = list(ZIM_REGIONS_MARKETS.keys())
    tokens = msg_low.split()
    det_reg = None
    for r in regions:
        if r.lower() in msg_low: det_reg = r; break
        if difflib.get_close_matches(r.lower(), tokens, n=1, cutoff=0.8): det_reg = r; break
        
    if not det_reg:
        return f"{persona_intro}🌤️ To give you accurate agronomic weather advice, please include your region (e.g., 'Weather in Harare')."
        
    # 2. Fetch Alerts (Global)
    alerts_data = rtdb.reference('climate_alerts').get() or {}
    
    # In a full system, this fetches user-specific or region-specific. We'll simulate checking global alerts
    # If alerts are stored by user_id, we check the admin global alerts or just find any matching region.
    region_alerts = []
    
    # Check if climate_alerts has dicts
    if isinstance(alerts_data, dict):
        for k, v in alerts_data.items():
            if isinstance(v, dict) and v.get('region', '').lower() == det_reg.lower():
                region_alerts.append(v)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict) and item.get('region', '').lower() == det_reg.lower():
                        region_alerts.append(item)
    elif isinstance(alerts_data, list):
        for item in alerts_data:
            if isinstance(item, dict) and item.get('region', '').lower() == det_reg.lower():
                region_alerts.append(item)
                
    if not region_alerts:
        return f"{persona_intro}🌤️ *Agronomic Weather: {det_reg}*\n\nConditions in {det_reg} are currently stable. Proceed with standard daily crop management and watering schedules."
        
    # Format the latest alert
    latest = region_alerts[-1]
    reply = f"{persona_intro}🌤️ *Agronomic Weather: {det_reg}*\n\n"
    reply += f"🌡️ *Condition:* {latest.get('condition', 'Unknown')} ({latest.get('temp', '--')}°C)\n"
    reply += f"💨 *Wind:* {latest.get('wind', '--')} km/h | 💧 *Humidity:* {latest.get('humidity', '--')}%\n\n"
    reply += f"⚠️ *{latest.get('title', 'Alert')}*\n💡 *Action:* {latest.get('advice', '')}"
    
    return reply

def handle_sms_subscription(user_phone, user_input, user_state, rtdb, session_data, user_uid):
    """
    Handles payment state transitions for standard SMS users in Zimbabwe via EcoCash/OneMoney.
    """
    if user_state == "AWAITING_PUSH_PKG":
        pkg_map = {'A': 'basic', 'B': 'standard', 'C': 'premium'}
        if user_input in pkg_map:
            selected_pkg = pkg_map[user_input]
            set_session_state(rtdb, user_phone, 'sms_subscription', step='AWAITING_PAYMENT_NUMBER', selected_pkg=selected_pkg)
            prices = {'basic': '$3', 'standard': '$5', 'premium': '$10'}
            return f"You selected {selected_pkg.title()} Pkg ({prices[selected_pkg]}). Reply with your mobile money number to pay via EcoCash/OneMoney (e.g., 0771234567)."
        return "Invalid selection. Please reply with A, B, or C."
        
    elif user_state == "AWAITING_PAYMENT_NUMBER":
        target_wallet = user_input.strip()
        selected_pkg = session_data.get('selected_pkg', 'basic')
        prices = {'basic': 3.0, 'standard': 5.0, 'premium': 10.0}
        amount = prices.get(selected_pkg, 3.0)
        
        try:
            from gateway_paynow import trigger_mobile_push
            result = trigger_mobile_push(target_wallet, amount, user_uid, selected_pkg)
            
            if result.get('success'):
                # Store the transaction info in a pending node for the webhook to resolve
                poll_url = result.get('poll_url')
                reference = result.get('reference')
                rtdb.reference(f'pending_transactions/{reference}').set({
                    'user_id': user_uid,
                    'phone': user_phone,
                    'amount': amount,
                    'plan_id': selected_pkg,
                    'status': 'awaiting_payment',
                    'poll_url': poll_url,
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
                clear_session_state(rtdb, user_phone)
                return "ZIMBOT | PIN prompt sent to your phone. Enter your PIN to complete subscription. Once paid, wait for confirmation SMS."
            else:
                return f"ZIMBOT | Gateway Error: {result.get('error', 'Unknown Error')}. Please try again later."
        except Exception as e:
            logger.error(f"Paynow push error: {e}", exc_info=True)
            return "ZIMBOT | Failed to initiate push. Please try again later."
        
    elif user_state == "AWAITING_MANUAL_PKG":
        pkg_map = {'A': 'basic', 'B': 'standard', 'C': 'premium'}
        if user_input in pkg_map:
            selected_pkg = pkg_map[user_input]
            set_session_state(rtdb, user_phone, 'sms_subscription', step='AWAITING_MANUAL_REF', selected_pkg=selected_pkg)
            prices = {'basic': '$3', 'standard': '$5', 'premium': '$10'}
            return f"PAYMENT | Send {prices[selected_pkg]} to EcoCash Merchant MerchantID: 123456. After paying, reply with your Tx Ref Code (e.g., MP260626.2150.C12345)."
        return "Invalid selection. Please reply with A, B, or C."
        
    elif user_state == "AWAITING_MANUAL_REF":
        reference_code = user_input.strip().upper()
        try:
            from gateway_paynow import verify_manual_reference
            is_valid = verify_manual_reference(reference_code)
        except Exception:
            is_valid = False
            
        if is_valid:
            eat_tz = timezone(timedelta(hours=3))
            expiry_date = (datetime.now(eat_tz) + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
            selected_pkg = session_data.get('selected_pkg', 'basic')
            
            rtdb.reference(f'users/{user_uid}').update({
                'subscription_tier': selected_pkg,
                'subscription_status': 'active',
                'subscription_expiry': expiry_date
            })
            clear_session_state(rtdb, user_phone)
            return f"ZIMBOT ACC | Payment verified! {selected_pkg.title()} Package active until {expiry_date[:10]}. Trade Profitably!"
        else:
            return "ZIMBOT | Invalid or unverified transaction code. Please double-check and reply with the correct reference."
            
    return "Session expired or invalid state. Reply 1 for Menu."

# ==========================================
# MAIN WEBHOOK HANDLER (CLEAN ROUTING)
# ==========================================


def handle_zimbot_request(incoming_msg, user_phone, rtdb, initiate_stk_push, system_pricing):
    import re
    # 1. CHANNEL DETECTION (Omni-Channel Core Engine)
    is_whatsapp = user_phone.startswith('whatsapp:')
    channel_type = 'whatsapp' if is_whatsapp else 'sms'
    
    # Clean phone number for database tracking
    clean_phone = user_phone.replace('whatsapp:', '').replace('+', '').strip()

    if channel_type == 'whatsapp':
        persona_intro = "🇿🇼 *ZIMBOT: Agricultural Market Intelligence Engine*\n\n"
    else:
        persona_intro = "ZIMBOT RPT - "

    msg_clean = incoming_msg.strip().upper().replace('[', '').replace(']', '')
    msg_low = incoming_msg.lower().strip()

    def send_response(text):
        if channel_type == 'sms':
            # Remove Markdown
            text = text.replace('*', '').replace('_', '')
            # Replace trend indicators
            text = text.replace('▲', '(Up)').replace('▼', '(Down)').replace('▬', '(Flat)')
            # Strip emojis (keep basic punctuation and alphanumeric)
            text = re.sub(r'[^\w\s\.,;:!?\-\(\)\$\/|]', '', text)
            
            # Professional Financial Abbreviations
            replacements = {
                'Regional Intelligence': 'REG',
                'Market Intelligence': 'MKT',
                'Commodity Intelligence': 'SPOT',
                'Targeted Intelligence': 'DATA',
                'Consultant Advice': 'Insight',
                'Agricultural Market Intelligence Engine': 'Ag-Intel',
                'Predicted to reach': 'Est Tgt',
                'Commodity': 'Asset',
                'Market': 'Mkt',
                'Town': 'Loc',
                'Price': 'Px',
                'Trend': 'Bias',
                'Average': 'Avg',
                'Hello, ': '',
                'Welcome to ': '',
                'I have analyzed all active hubs in the ': 'Hubs in ',
                ' network for you:': ':',
                'Here is the full commodity list for ': 'Data for ',
                ' as of today:': ':',
                'National spot prices across Zimbabwe:': 'National Spot:'
            }
            for k, v in replacements.items():
                text = re.sub(re.escape(k), v, text, flags=re.IGNORECASE)
                
            # Layout adjustment: convert bullet points and newlines into a professional ticker tape format
            text = text.replace('• ', '')
            text = re.sub(r'\n+', ' | ', text).strip(' |')
            text = re.sub(r'\s+\|\s+', ' | ', text)
            
            # Add Menu Hint cleanly
            if not re.search(r'reply.*?1', text, re.IGNORECASE):
                text += " | Rep 1: Menu"
                
            # Truncate
            if len(text) > 160:
                text = text[:157] + "..."
                
        resp = MessagingResponse()
        resp.message(text)
        return str(resp)

    try:
        # 1. ROBUST IDENTITY FETCH
        user_uid = f"wa_{clean_phone}"
        user_data = rtdb.reference(f'users/{user_uid}').get()
        if not user_data:
            all_users = rtdb.reference('users').get() or {}
            if isinstance(all_users, list):
                all_users = {str(i): v for i, v in enumerate(all_users) if v is not None}
            for uid, data in all_users.items():
                if not isinstance(data, dict): continue
                db_phone = str(data.get('phone', '')).replace('+', '').strip()
                if db_phone and (db_phone in clean_phone or clean_phone in db_phone):
                    user_data = data; user_uid = uid; break
        
        lang = user_data.get('language', 'en') if user_data else 'en'
        user_name = user_data.get('full_name', 'Valued Farmer') if user_data else 'Valued Farmer'
        sub_status = user_data.get('subscription_status', 'inactive') if user_data else 'inactive'
        
        # 2. GLOBAL ESCAPES
        if msg_clean in ['MENU', 'HOME', 'CANCEL', 'RESET']:
            clear_session_state(rtdb, clean_phone)
            menu_text = f"{get_zim_text('welcome', lang, name=user_name)}\n{get_zim_text('menu_prompt', lang)}\n"
            for i in range(1, 9): menu_text += f"{get_zim_text(f'opt{i}', lang)}\n"
            return send_response(f"{persona_intro}{menu_text}")

        session_data = get_session_state(rtdb, clean_phone) or {}
        current_state = session_data.get('current_state')
        intent = get_zim_intent(incoming_msg)

        # 3. CONTEXTUAL STATE EVALUATION
        if current_state:
            if intent in ['1', '2', '3', '4', '5', '6', '7', '8']:
                clear_session_state(rtdb, clean_phone)
                current_state = None
            else:
                if current_state == 'registration':
                    reply_text = handle_registration(msg_clean, clean_phone, session_data, rtdb, lang, user_uid)
                    return send_response(reply_text)
                elif current_state == 'faq':
                    reply_text = handle_faq(msg_clean, clean_phone, session_data, rtdb)
                    return send_response(reply_text)
                elif current_state == 'payments':
                    reply_text = handle_payments(msg_clean, clean_phone, session_data, rtdb, lang, system_pricing, initiate_stk_push, user_uid, user_name)
                    return send_response(reply_text)
                elif current_state == 'sms_subscription':
                    step = session_data.get('step')
                    reply_text = handle_sms_subscription(clean_phone, msg_clean, step, rtdb, session_data, user_uid)
                    return send_response(reply_text)
                elif current_state == 'change_lang':
                    lang_map = {'A': 'en', 'B': 'sn', 'C': 'nd', 'D': 'ny', 'E': 'to', 'F': 'st'}
                    if msg_clean in lang_map:
                        new_lang = lang_map[msg_clean]
                        rtdb.reference(f'users/{user_uid}').update({'language': new_lang})
                        clear_session_state(rtdb, clean_phone)
                        reply_text = get_zim_text('lang_changed', new_lang)
                        return send_response(reply_text)

        # 4. INTENT ROUTING
        if intent:
            if intent == '1':
                if user_data: reply_text = get_zim_text('already_reg', lang, name=user_name)
                else: 
                    set_session_state(rtdb, clean_phone, 'registration', step='ask_name')
                    reply_text = get_zim_text('ask_name', lang)
            elif intent == '2': reply_text = f"{persona_intro}{get_zim_text('about', lang)}"
            elif intent == '3': reply_text = f"{persona_intro}{get_zim_text('terms', lang)}"
            elif intent == '4':
                set_session_state(rtdb, clean_phone, 'faq', step='category_selection')
                reply_text = "🌾 *FREQUENTLY ASKED QUESTIONS*\n\n[A] General Information & Markets Covered\n[B] Bot Capabilities & Market Intelligence\n[C] Subscriptions, Pricing & Access\n\nReply with a letter, or type your question!"
            elif intent in ['5', '6']:
                if channel_type == 'sms':
                    if intent == '5':
                        reply_text = "ZIMBOT PKGS | A: Basic ($3/mo) | B: Standard ($5/mo) | C: Premium ($10/mo). Reply with Letter to choose."
                        set_session_state(rtdb, clean_phone, 'sms_subscription', step='AWAITING_PUSH_PKG')
                    else:
                        reply_text = "ZIMBOT PKGS | A: Basic ($3/mo) | B: Standard ($5/mo) | C: Premium ($10/mo). Reply with Letter for manual EcoCash payment."
                        set_session_state(rtdb, clean_phone, 'sms_subscription', step='AWAITING_MANUAL_PKG')
                else:
                    p_text = f"{get_zim_text('pricing_intro', lang)}\n\n{get_zim_text('seed', lang)}\n\n{get_zim_text('growth', lang)}\n\n{get_zim_text('harvest', lang)}\n\n{get_zim_text('select_plan', lang)}"
                    reply_text = f"{persona_intro}{p_text}"
                    set_session_state(rtdb, clean_phone, 'payments', step='select_package')
            elif intent == '7':
                reply_text = f"{persona_intro}{SUPPORT_MESSAGE.get(lang, SUPPORT_MESSAGE['en'])}"
            elif intent == '8' or intent == 'unsubscribe':
                if not user_data:
                    reply_text = "You are not currently registered in my system."
                else:
                    unsub_msgs = {'en': "I am sad to see you go. Your profile has been removed. You can re-register anytime by typing 'JOIN'.", 'sn': "Ndine urombo kukuonai muchienda. Nhoroondo yenyu yabviswa. Munogona kunyoresa zvakare nekunyora 'JOIN'.", 'nd': "Ngibuhlungu ukukubona uuhamba. Iphrofayili yakho isusiwe. Ungaphinda ubhalise ngokubhala 'JOIN'."}
                    reply_text = unsub_msgs.get(lang, unsub_msgs['en'])
                    rtdb.reference(f'users/{user_uid}').delete()
                    clear_session_state(rtdb, clean_phone)
            elif intent == 'change_lang':
                set_session_state(rtdb, clean_phone, 'change_lang')
                reply_text = get_zim_text('ask_lang', lang)
            elif intent == 'menu':
                menu_text = f"{get_zim_text('welcome', lang, name=user_name)}\n{get_zim_text('menu_prompt', lang)}\n"
                for i in range(1, 9): menu_text += f"{get_zim_text(f'opt{i}', lang)}\n"
                return send_response(f"{persona_intro}{menu_text}")
            
            return send_response(reply_text)

        # 5. NATURAL LANGUAGE ROUTING
        # Check Whitelist
        is_whitelisted = False
        whitelist_data = rtdb.reference('whatsapp_whitelist').get() or {}
        for wid, wdata in whitelist_data.items():
            wphone = str(wdata.get('phone', '') if isinstance(wdata, dict) else wdata).strip().replace('+', '')
            if wphone and (wphone in clean_phone or clean_phone in wphone):
                is_whitelisted = True; break

        agri_keywords = ['maize', 'corn', 'chibage', 'price', 'mutengo', 'harare', 'mbare', 'bulawayo', 'gweru', 'mutare', 'market', 'weather', 'rain', 'mvura', 'beans', 'soya', 'cattle', 'livestock']
        if any(k in msg_low for k in agri_keywords):
            if sub_status == 'active' or is_whitelisted:
                if any(k in msg_low for k in ['weather', 'kunze', 'climate', 'rain', 'mvura']):
                    reply_text = process_weather_query(msg_low, lang, rtdb, persona_intro)
                else:
                    reply_text = process_intelligence_query(msg_low, lang, rtdb, persona_intro)
            else:
                reply_text = get_zim_text('sub_req', lang, name=user_name) + "\n\n" + get_zim_text('pricing_intro', lang) + "\n" + get_zim_text('seed', lang) + "\n" + get_zim_text('growth', lang) + "\n" + get_zim_text('harvest', lang)
            return send_response(reply_text)

        # 6. FAQ & FALLBACK
        nl_faq = get_nl_faq_answer(msg_low)
        if nl_faq:
            return send_response(nl_faq)

        reply_text = f"I didn't quite catch that, {user_name}. You can ask for a crop price (e.g., 'Maize in Harare') or reply with 'MENU' to see your options."
        return send_response(reply_text)

    except Exception as e:
        logger.error(f"Zim Bot Critical Error: {e}", exc_info=True)
        return send_response(get_zim_text('error', 'en'))


def generate_zim_market_alert(affected_crops_info):
    """Generates broadcast text for active market shifts."""
    alert_text = "⚠️ *ALERT: ZIMBOT MARKET UPDATE* ⚠️\n\nSignificant price shifts detected in the Zimbabwe agricultural network:\n\n"
    for crop in affected_crops_info:
        trend = crop.get('trend', 'stable'); commodity = crop.get('commodity'); price = crop.get('price')
        if trend == 'up': alert_text += f"🚀 *{commodity}:* Prices are RISING! Now at {price}. Sell now to maximize profit.\n"
        elif trend == 'down': alert_text += f"📉 *{commodity}:* Prices are DROPPING! Now at {price}. Hold your stock if possible.\n"
        else: alert_text += f"⚖️ *{commodity}:* Prices are STABLE at {price}.\n"
    alert_text += "\n*Action:* Review your trading strategy immediately based on these insights.\n\n_Stay informed with ZimBot._"
    return alert_text


from twilio.rest import Client

def dispatch_scheduled_reports(user_list, report_data):
    """
    Dispatches scheduled updates to the configured Tiers based on the day.
    Bypasses matplotlib completely by utilizing text-only ticker constraints for SMS.
    """
    # Initialize Twilio client using environment variables
    client = Client(os.environ.get('TWILIO_ACCOUNT_SID'), os.environ.get('TWILIO_AUTH_TOKEN'))
    
    # Your official Twilio number
    twilio_number = "+18175105460"
    
    day_str = report_data.get('day', 'FRI').upper()[:3]
    full_day_str = report_data.get('day', 'FRIDAY').upper()
    
    for user in user_list:
        phone = user['phone'] # e.g., "+263..."
        channel = user['preferred_channel'].lower() # "sms", "whatsapp", or "email"
        name = user.get('name', 'Farmer')
        
        try:
            if channel == "sms":
                # --- PURE SMS TICKER TAPE (Zero Images, Under 160 Characters) ---
                sms_body = (
                    f"ZIMBOT {day_str} RPT | Asset: {report_data['asset']} | "
                    f"Mkt: {report_data['market']} | Px: {report_data['price']} | "
                    f"Bias: {report_data['bias']} | Insight: {report_data['sms_insight']} | "
                    f"Rep 1: Menu"
                )
                # Strict programmatic guardrail for billing
                sms_body = sms_body[:160] 
                
                client.messages.create(
                    body=sms_body,
                    from_=twilio_number,
                    to=phone
                )
                print(f"Ticker SMS sent to {phone}")
                
            elif channel == "whatsapp":
                # --- RICH WHATSAPP TEXT (Full prose, markdown, and emojis) ---
                whatsapp_body = (
                    f"🇿🇼 *ZIMBOT: {full_day_str} STRATEGIC INTELLIGENCE* 🇿🇼\n\n"
                    f"Hello {name}, here is your elite scheduled analysis:\n\n"
                    f"🌾 *Asset:* {report_data['asset']}\n"
                    f"📍 *Market:* {report_data['market']}\n"
                    f"💰 *Current Px:* {report_data['price']}\n"
                    f"📈 *Market Bias:* {report_data['whatsapp_bias_symbol']} {report_data['bias']}\n\n"
                    f"💡 *Strategic Insight:* {report_data['whatsapp_insight']}\n\n"
                    f"Reply *[1]* to view your account options or main menu."
                )
                
                client.messages.create(
                    body=whatsapp_body,
                    from_=f"whatsapp:{twilio_number}",
                    to=f"whatsapp:{phone}"
                )
                print(f"Rich WhatsApp report sent to {phone}")
                
            elif channel == "email":
                # --- STANDARD EMAIL ROUTE ---
                # Call your existing custom email function here
                # send_email_report(user['email'], report_data)
                print(f"Email report sent to {user.get('email')}")
                
        except Exception as e:
            print(f"Failed to dispatch {full_day_str} report to {phone} via {channel}: {str(e)}")
