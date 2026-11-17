import gradio as gr

def respond(question: str, grade: str):
    return f"[{grade}] 입력된 문제:\n{question}\n\n(RAG 및 추론 모델 연결 예정)"

with gr.Blocks(title="K-12 Math RAG Tutor") as demo:
    gr.Markdown("# 초3~고3 수학 RAG 풀이 도우미")
    grade_dd = gr.Dropdown(
        choices=["e3", "e4", "e5", "e6", "m1", "m2", "m3", "h1", "h2", "h3"],
        value="h1",
        label="학년 선택",
    )
    q_box = gr.Textbox(label="수학 문제 입력", lines=6)
    btn = gr.Button("풀이 생성", variant="primary")
    out_box = gr.Textbox(label="풀이 결과", lines=12)
    btn.click(respond, inputs=[q_box, grade_dd], outputs=out_box)

if __name__ == "__main__":
    demo.launch()
