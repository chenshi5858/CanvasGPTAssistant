document.addEventListener("DOMContentLoaded", (event) => {
    const messageBox = document.querySelector(".input_mensaje");
    const sendButton = document.querySelector(".boton_enviar");
    const resetConversationButton = document.getElementById("resetConversationButton");
    const scrollButton = document.getElementById("scrollButton"); // Seleccionar el botón correctamente
    const messageContainer = document.querySelector(".mostrador_mensajes"); // Contenedor de mensajes

    const scrollToBottom = () => {
        messageContainer.scrollTop = messageContainer.scrollHeight; // Desplazar al final
    };

    const createWaitingMsg = () => {
        const waitingContainer = document.createElement("div");
        waitingContainer.className = "gpt waiting_msg";
        waitingContainer.innerHTML = `
            Estoy trabajando en tu respuesta, esto puede tardar unos segundos
            <span class="waiting_dots" aria-hidden="true">
                <span>.</span><span>.</span><span>.</span>
            </span>
        `;
        document.querySelector(".mostrador_mensajes").appendChild(waitingContainer);
        scrollToBottom();
        return waitingContainer;
    };

    const sendMessage = () => {
        const usermsg = messageBox.value.trim();
        if (usermsg !== "") {
            displayMsg(usermsg, "user");
            messageBox.value = "";
            const waitingMsg = createWaitingMsg();
            const csrfToken = document.querySelector("[name=csrfmiddlewaretoken]").value;

            axios.post(
                "/chatgpt_response/",
                {
                    message: usermsg,
                    canvas_user: messageBox.dataset.user,
                    course: messageBox.dataset.course,
                    login: messageBox.dataset.login,
                    agent: messageBox.dataset.agent,
                    course_title: messageBox.dataset.title,
                },
                {
                    headers: {
                        "X-CSRFToken": csrfToken,
                    },
                }
            )
                .then((response) => {
                    waitingMsg.remove();
                    const gptResponse = response.data.reply;
                    displayMsg(gptResponse, "gpt");
                })
                .catch((error) => {
                    waitingMsg.remove();
                    console.error(error);
                    displayMsg(
                        "Error: No se pudo conectar con el servidor",
                        "gpt"
                    );
                });
        }
    };
    sendButton.addEventListener("click", sendMessage);

    messageBox.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            sendMessage();
        }
    });

    scrollButton.addEventListener("click", scrollToBottom);

    const resetConversation = () => {
        const csrfToken = document.querySelector("[name=csrfmiddlewaretoken]").value;
        if (messageBox.dataset.user && messageBox.dataset.user.length > 0) {
            displayMsg("Reset disponible solo en modo anónimo.", "gpt");
            return;
        }
        axios.post(
            "/chatgpt_reset_anonymous/",
            {
                agent: messageBox.dataset.agent,
            },
            {
                headers: {
                    "X-CSRFToken": csrfToken,
                },
            }
        )
            .then(() => {
                messageContainer.innerHTML = "";
                displayMsg("Conversación reiniciada. Puedes volver a probar el agente.", "gpt");
            })
            .catch((error) => {
                console.error(error);
                displayMsg("Error al reiniciar la conversación.", "gpt");
            });
    };

    if (resetConversationButton) {
        resetConversationButton.addEventListener("click", resetConversation);
    }

    function displayMsg(msg, sender) {
        const msgContainer = document.createElement("div");
        msgContainer.className = sender;
        msgContainer.innerHTML = msg;
        console.log(msg);
        document.querySelector(".mostrador_mensajes").appendChild(msgContainer);
        renderMathInElement(msgContainer, {
            delimiters: [
                { left: "\\(", right: "\\)", display: false },
                { left: "\\[", right: "\\]", display: true },
            ]
        });
        scrollToBottom();
    }
    scrollToBottom();
    renderMathInElement(document.querySelector(".mostrador_mensajes"), {
        delimiters: [
            { left: "\\(", right: "\\)", display: false },
            { left: "\\[", right: "\\]", display: true },
        ]
    });
});
