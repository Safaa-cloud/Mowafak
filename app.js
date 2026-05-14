const acceptBtn =
document.getElementById("acceptBtn");

const recordBtn =
document.getElementById("recordBtn");

const stopBtn =
document.getElementById("stopBtn");

const uploadBtn =
document.getElementById("uploadBtn");

const downloadBtn =
document.getElementById("downloadBtn");

const audioPlayer =
document.getElementById("audioPlayer");

const statusText =
document.getElementById("status");

const questionTitle =
document.getElementById("questionTitle");

const questionText =
document.getElementById("questionText");

const progressText =
document.getElementById("progressText");

recordBtn.disabled = true;

let mediaRecorder;

let audioChunks = [];

let audioBlob;

const questions = [

    "Tell us about yourself.",

    "Describe a project you worked on.",

    "What technologies have you used?",

    "How do you solve programming bugs?",

    "Why do you want this role?"

];

let currentQuestion = 0;

function loadQuestion() {

    questionTitle.innerText =
        `Question ${currentQuestion + 1}`;

    questionText.innerText =
        questions[currentQuestion];

    progressText.innerText =
        `Question ${currentQuestion + 1} of ${questions.length}`;

}

loadQuestion();

acceptBtn.onclick = () => {

    recordBtn.disabled = false;

    alert("Consent Accepted");

};

recordBtn.onclick = async () => {

    try {

        const stream =
        await navigator.mediaDevices.getUserMedia({
            audio: true
        });

        mediaRecorder =
        new MediaRecorder(stream);

        audioChunks = [];

        mediaRecorder.start();

        statusText.innerText =
            "🔴 Recording...";

        mediaRecorder.ondataavailable =
        (event) => {

            audioChunks.push(event.data);

        };

        mediaRecorder.onstop = () => {

            audioBlob =
            new Blob(audioChunks, {
                type: 'audio/wav'
            });

            const audioURL =
            URL.createObjectURL(audioBlob);

            audioPlayer.src = audioURL;

            statusText.innerText =
                "✅ Recording Finished";

            downloadBtn.onclick = () => {

                const a =
                document.createElement("a");

                a.href = audioURL;

                a.download =
                "candidate_answer.wav";

                a.click();

            };

        };

    } catch (error) {

        alert("Microphone access denied");

        console.log(error);

    }

};

stopBtn.onclick = () => {

    if (mediaRecorder) {

        mediaRecorder.stop();

    }

};

uploadBtn.onclick = () => {

    statusText.innerText =
        "Uploading...";

    setTimeout(() => {

        statusText.innerText =
            "✅ Uploaded Successfully";

        currentQuestion++;

        if (currentQuestion < questions.length) {

            loadQuestion();

        } else {

            questionTitle.innerText =
                "Interview Completed";

            questionText.innerText =
                "Thank you for your time.";

            progressText.innerText =
                "Done";

        }

    }, 2000);

};