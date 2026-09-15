import torch
from transformers import TrOCRProcessor, VisionEncoderDecoderModel
import numpy as np
import string

class TextReader:
    """
    There are 3 main models to choose from, small, base and large.
    """
    def __init__(self, model_name="microsoft/trocr-large-handwritten", device=None):
        # load directly from Hugging Face Hub
        self.processor = TrOCRProcessor.from_pretrained(model_name)
        self.model = VisionEncoderDecoderModel.from_pretrained(model_name)

        # pick device
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)
        self.model.eval()
        print(f'using: {self.device}')

    def read(self, image):
    

        pixel_values = self.processor(image, return_tensors="pt").pixel_values.to(self.device)

        outputs = self.model.generate(
            pixel_values,
            max_new_tokens=30,
            output_scores=True,
            return_dict_in_generate=True
        )

        generated_ids = outputs.sequences
        scores = outputs.scores  # list of logits for each generated token step

        generated_text = self.processor.batch_decode(generated_ids, skip_special_tokens=True)[0]

        probs = []
        for i, logits in enumerate(scores):
            softmax_probs = torch.softmax(logits, dim=-1)
            token_id = generated_ids[0, i + 1]  # +1 because first token is input
            token_prob = softmax_probs[0, token_id].item()
            probs.append(token_prob)

        avg_confidence = sum(probs) / len(probs) if probs else 0
        CONFIDENCE_THRESHOLD = 0.6

        if avg_confidence < CONFIDENCE_THRESHOLD:
            return "Could not read text"
        
        else:
            #clean the text
            cleaned = self.clean_text(generated_text)
            print(cleaned)
            return cleaned
        


    def clean_text(self, text):
        # Convert to lowercase
        text = text.lower()
        # Remove trailing punctuation and whitespace
        return text.rstrip(string.punctuation + " ")


_text_reader_instance = None


def get_text_reader():
    """Return a process-wide cached TextReader.

    Loading trocr-large-handwritten from disk/HF cache takes a long time; reusing
    one instance across analyses run in the same app session avoids reloading it
    every time the user starts a new analysis.
    """
    global _text_reader_instance
    if _text_reader_instance is None:
        _text_reader_instance = TextReader()
    return _text_reader_instance

