document.addEventListener("DOMContentLoaded", (event) => {
    messageBox = document.querySelector(".input_mensaje")
    sendButton = document.querySelector(".boton_enviar")

    sendButton.addEventListener('click', () => {
        const usermsg = messageBox.value;
        if (usermsg.trim()!=""){
            displayMsg(usermsg, "user");
            messageBox.value = "";
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

            axios.post("/chatgpt_response/", {
                message: usermsg
            },{
                headers: {
                    'X-CSRFToken': csrfToken
                }
            })
            .then((response)=>{
                const gptResponse =response.data.reply;
                displayMsg(gptResponse, "gpt")
            })
            .catch(error=>{
                console.error(error);
                displayMsg('Error: No se pudo conectar con el servidor', 'chatgpt');
            })
        }
    })


    function displayMsg(msg, sender){
        const msgContainer = document.createElement('div');
        msgContainer.className = sender;
        msgContainer.textContent = msg;
        document.querySelector(".mostrador_mensajes").appendChild(msgContainer);
    }
});
