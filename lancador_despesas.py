import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO
import locale
import pytesseract
from PIL import Image
import re
from fpdf import FPDF

# --- Configuração do Tesseract ---
try:
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
except Exception:
    st.error("Tesseract não encontrado. Verifique o caminho da instalação no código.")

# --- Configuração da Página e Localização ---
st.set_page_config(page_title="Lançador de Despesas", page_icon="💸")
try:
    locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
except locale.Error:
    st.warning("Localização 'pt_BR' não encontrada. O mês pode aparecer em inglês.")

# --- Listas de Opções ---
PROJETOS = ["Compass - Executive Management"]
PROFISSIONAIS = ["Lucas Ballen"]
DESPESAS_OPCOES = ["Alimentação", "Aluguel", "Capacitação", "Combustível", "Estacionamento", "Passagem - Avião", "Passagem - Onibus", "Taxi", "Uber Empresarial"]
ATIVIDADES_OPCOES = ["Acompanhamento de projetos", "Atividade Interna", "Atividades Comerciais em Geral", "Atividades de Negócios em Geral", "Certificação/Capacitação", "Deslocamento", "Reunião Cliente", "Reunião Compasso", "Treinamento a Clientes", "Treinamento Interno"]

# --- Funções de Lógica ---
# CORREÇÃO: Removido o @st.cache_data que causava o problema de não reler a imagem.
def extrair_dados_nf(imagem_bytes):
    """Usa OCR para extrair data e valor, com otimizações e feedback de sucesso."""
    try:
        imagem = Image.open(BytesIO(imagem_bytes))
        imagem.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
        imagem = imagem.convert('L')

        texto_nf = pytesseract.image_to_string(imagem, lang='por')
        
        data_extraida, valor_extraido = None, None

        padrao_data = re.search(r'(\d{2}[/.-]\d{2}[/.-]\d{2,4})', texto_nf)
        if padrao_data:
            data_str = re.sub(r'[.-]', '/', padrao_data.group(1))
            try:
                data_extraida = datetime.strptime(data_str, '%d/%m/%Y').date()
            except ValueError:
                data_extraida = datetime.strptime(data_str, '%d/%m/%y').date()

        padrao_valor = re.search(r'(?:VALOR\s+TOTAL|TOTAL\s+A\s+PAGAR|TOTAL|SUBTOTAL)\s*R?\$\s*([\d,]+\.?\d{2})', texto_nf, re.IGNORECASE)
        if padrao_valor:
            valor_str = padrao_valor.group(1).replace('.', '').replace(',', '.')
            valor_extraido = float(valor_str)
        
        return data_extraida, valor_extraido
    except Exception:
        return None, None

def gerar_pdf_otimizado(lista_de_despesas):
    pdf = FPDF()
    for despesa in lista_de_despesas:
        if despesa.get('Imagem'):
            pdf.add_page()
            titulo = f"Despesa: {despesa['Despesa']} - Data: {despesa['Data'].strftime('%d/%m/%Y')} - Valor: R$ {despesa['Valor']:.2f}"
            pdf.set_font("Arial", size=12)
            pdf.cell(200, 10, txt=titulo, ln=True, align='C')
            imagem_original = Image.open(BytesIO(despesa['Imagem']))
            buffer_otimizado = BytesIO()
            imagem_original.save(buffer_otimizado, format="JPEG", quality=80, optimize=True)
            pdf.image(buffer_otimizado, x=10, y=30, w=190)
    return bytes(pdf.output())

@st.cache_data
def convert_df_to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Despesas')
    return output.getvalue()

# --- Inicialização da Sessão ---
if 'lista_despesas' not in st.session_state:
    st.session_state.lista_despesas = []
if 'ocr_date' not in st.session_state:
    st.session_state.ocr_date = datetime.now().date()
if 'ocr_value' not in st.session_state:
    st.session_state.ocr_value = 0.01

# --- Interface Gráfica ---
st.title("💸 Lançador Inteligente de Despesas")
st.subheader("1. Adicione a Nota Fiscal")

imagem_bytes = None
with st.expander("📷 Tirar Foto com a Câmera"):
    foto_camera = st.camera_input("Aponte a câmera para a nota fiscal", key="camera")
    if foto_camera:
        imagem_bytes = foto_camera.getvalue()

with st.expander("📎 Anexar Arquivo do Celular"):
    arquivo_anexado = st.file_uploader("Selecione a imagem da sua NF", type=['jpg', 'png', 'jpeg'], key="uploader")
    if arquivo_anexado:
        imagem_bytes = arquivo_anexado.getvalue()

if imagem_bytes:
    with st.spinner('Lendo a nota fiscal (otimizado)...'):
        data_lida, valor_lido = extrair_dados_nf(imagem_bytes)
    
    if data_lida and valor_lido:
        st.session_state.ocr_date = data_lida
        st.session_state.ocr_value = valor_lido
        st.success("Nota fiscal lida! Verifique os campos abaixo.")
    else:
        st.warning("Não foi possível ler a data e/ou o valor da nota. Por favor, preencha manualmente.")

st.subheader("2. Verifique os dados e preencha o restante")
with st.form("form_despesas"):
    col1, col2 = st.columns(2)
    with col1:
        projeto = st.selectbox("Projeto*", options=PROJETOS)
        data = st.date_input("Data*", value=st.session_state.ocr_date)
        despesa_tipo = st.selectbox("Despesa*", options=DESPESAS_OPCOES)
        valor_formulario = st.number_input("Valor (R$)*", value=st.session_state.ocr_value, min_value=0.01, format="%.2f")
    with col2:
        profissional = st.selectbox("Profissional*", options=PROFISSIONAIS)
        atividade = st.selectbox("Atividade*", options=ATIVIDADES_OPCOES)
        observacoes_usuario = st.text_area("Observações")
    almoco_cliente = st.toggle("Foi almoço com cliente?", help="Marque para isenção do teto de gastos.")
    submitted = st.form_submit_button("Adicionar Despesa ao Relatório")

    if submitted:
        valor_a_registrar, observacao_final, pode_adicionar = valor_formulario, observacoes_usuario, True
        if despesa_tipo == "Alimentação" and not almoco_cliente:
            despesas_alimentacao_dia = [d for d in st.session_state.lista_despesas if d['Data'] == data and d['Despesa'] == 'Alimentação' and not d['AlmocoCliente']]
            soma_atual_do_dia = sum(d['Valor'] for d in despesas_alimentacao_dia)
            if soma_atual_do_dia >= 70.00:
                st.error(f"Não é possível adicionar. Limite de R$ 70,00 para o dia {data.strftime('%d/%m/%Y')} atingido.")
                pode_adicionar = False
            else:
                limite_restante = 70.00 - soma_atual_do_dia
                if valor_formulario > limite_restante:
                    valor_a_registrar = limite_restante
                    msg_sistema = f"Valor original R$ {valor_formulario:.2f} ajustado para R$ {valor_a_registrar:.2f} (teto diário)."
                    observacao_final = f"{observacoes_usuario} | {msg_sistema}".strip() if observacoes_usuario else msg_sistema
        if pode_adicionar:
            nova_despesa = {'Projeto': projeto, 'Profissional': profissional, 'Data': data, 'Despesa': despesa_tipo, 'Atividade': atividade, 'Valor': valor_a_registrar, 'Observações': observacao_final, 'AlmocoCliente': almoco_cliente, 'Imagem': imagem_bytes}
            st.session_state.lista_despesas.append(nova_despesa)
            st.success(f"Despesa de R$ {valor_a_registrar:.2f} adicionada!")
            st.session_state.ocr_date = datetime.now().date()
            st.session_state.ocr_value = 0.01
            st.experimental_rerun()

st.subheader("3. Relatório de Despesas")
if st.session_state.lista_despesas:
    df_temp = pd.DataFrame(st.session_state.lista_despesas).sort_values(by='Data')
    dados_para_exibicao = [{'Projeto': row['Projeto'], 'Profissional': row['Profissional'], 'Data': row['Data'].strftime('%d-%b-%y'), 'Despesa': row['Despesa'], 'Atividade': row['Atividade'], 'Valor': row['Valor'], 'Observações': row['Observações']} for index, row in df_temp.iterrows()]
    colunas_excel = ['Projeto', 'Profissional', 'Data', 'Despesa', 'Atividade', 'Valor', 'Observações']
    df_final = pd.DataFrame(dados_para_exibicao)[colunas_excel]
    st.dataframe(df_final.style.format({'Valor': "R$ {:.2f}"}))
    
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        excel_file = convert_df_to_excel(df_final)
        st.download_button(label="📥 Baixar Relatório em Excel", data=excel_file, file_name=f"Relatorio_Despesas_{datetime.now().strftime('%Y%m%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    
    with col_btn2:
        pdf_file = gerar_pdf_otimizado(st.session_state.lista_despesas)
        st.download_button(label="📄 Baixar PDF com as Notas", data=pdf_file, file_name=f"Comprovantes_{datetime.now().strftime('%Y%m%d')}.pdf", mime="application/pdf")