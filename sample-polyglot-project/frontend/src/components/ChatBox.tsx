import React, { useState } from 'react';

export const ChatBox = () => {
    const [msg, setMsg] = useState("");

    const send = () => {
        console.log("Sending: ", msg);
        setMsg("");
    };

    return (
        <div>
            <input value={msg} onChange={e => setMsg(e.target.value)} />
            <button onClick={send}>Send</button>
        </div>
    );
};
