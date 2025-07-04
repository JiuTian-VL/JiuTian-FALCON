import argparse
import torch
import os
import json
from tqdm import tqdm
import shortuuid

from jiutian.constants import IMAGE_TOKEN_INDEX, DEFAULT_IMAGE_TOKEN, DEFAULT_IM_START_TOKEN, DEFAULT_IM_END_TOKEN
from jiutian.conversation import conv_templates, SeparatorStyle
from jiutian.model.builder import load_pretrained_model
from jiutian.utils import disable_torch_init
from jiutian.mm_utils import tokenizer_image_token, get_model_name_from_path, KeywordsStoppingCriteria
from jiutian.eval.model_infer import JiutianHDInfer

from PIL import Image
import math


def split_list(lst, n):
    """Split a list into n (roughly) equal-sized chunks"""
    chunk_size = math.ceil(len(lst) / n)  # integer division
    return [lst[i:i+chunk_size] for i in range(0, len(lst), chunk_size)]


def get_chunk(lst, n, k):
    chunks = split_list(lst, n)
    return chunks[k]


def eval_model(args):
    # Model
    disable_torch_init()

    model_name = get_model_name_from_path(args.model_path)
    model_infer = JiutianHDInfer(
        model_path=args.model_path,
        model_base=args.model_base,
        anchors='grid_9',
        add_global_img=True,
        add_textual_crop_indicator=True,
        do_sample=args.do_sample,
        temperature=args.temperature,
        max_new_tokens=args.max_new_tokens,
        num_beams=args.num_beams,
        top_p=args.top_p,
        conv_mode=args.conv_mode,
    )

    questions = json.load(open(os.path.expanduser(args.question_file), "r"))
    questions = get_chunk(questions, args.num_chunks, args.chunk_idx)

    answers_file = os.path.expanduser(args.answers_file)
    os.makedirs(os.path.dirname(answers_file), exist_ok=True)
    ans_file = open(answers_file, "w")

    for i, line in enumerate(tqdm(questions)):
        idx = line["id"]
        question = line['conversations'][0]
        query = question['value']
        query = query.replace('<image>', '').strip()

        if 'image' in line:
            images = os.path.join(args.image_folder, line["image"])
            query = DEFAULT_IMAGE_TOKEN + '\n' + query
        else:
            images = None

        if args.single_pred_prompt:
            single_pred_prompt = "Answer with the option's letter from the given choices directly."
            query = query + '\n' + single_pred_prompt

        cur_prompt = query
        outputs = model_infer.inference(images, query)

        if args.answer_prompter:
            outputs_reasoning = outputs
            query = query + outputs_reasoning + ' ###\nANSWER:'
            outputs = model_infer.inference(images, query)
            outputs = outputs_reasoning + '\n The answer is ' + outputs

        ans_id = shortuuid.uuid()
        ans_file.write(json.dumps({"question_id": idx,
                                   "prompt": cur_prompt,
                                   "text": outputs,
                                   "answer_id": ans_id,
                                   "model_id": model_name,
                                   "metadata": {}}) + "\n")
        ans_file.flush()
    ans_file.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", type=str, default="facebook/opt-350m")
    parser.add_argument("--model-base", type=str, default=None)
    parser.add_argument("--image-folder", type=str, default="")
    parser.add_argument("--question-file", type=str, default="tables/question.json")
    parser.add_argument("--answers-file", type=str, default="answer.jsonl")
    parser.add_argument("--conv-mode", type=str, default="jiutian_v0")
    parser.add_argument("--num-chunks", type=int, default=1)
    parser.add_argument("--chunk-idx", type=int, default=0)
    parser.add_argument("--do_sample", type=bool, default=False)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--top_p", type=float, default=1.0)
    parser.add_argument("--num_beams", type=int, default=1)
    parser.add_argument("--max_new_tokens", type=int, default=1024)
    parser.add_argument("--answer-prompter", action="store_true")
    parser.add_argument("--single-pred-prompt", action="store_true")
    args = parser.parse_args()

    eval_model(args)
