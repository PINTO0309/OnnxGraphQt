# [WIP]OnnxGraphQt

ONNX model visualizer with NodeGraphQt.

## Requirements
- [NodeGraphQt](https://github.com/jchanvfx/NodeGraphQt)
- PySide2
- NetworkX
- Numpy
- onnx
- onnx_graphsurgeon


## Install
```bash
git clone https://github.com/fateshelled/OnnxGraphQt
cd OnnxGraphQt
python3 -m pip install -r requirements.txt
```

## Usage
```bash
cd OnnxGraphQt
python3 onnxgraphqt/main.py
```

## ToDo
- [x] Visualize Model
- [x] Export Model
- [ ] Combine Network [1. snc4onnx]
- [ ] Extract Network [2. sne4onnx]
- [ ] Delete Node [3. snd4onnx]
- [x] Constant Value Shrink [4. scs4onnx]
- [x] Generate Operation [5. sog4onnx]
- [ ] Modify Operator Parameter [6. sam4onnx]
- [x] Change Opset [7. soc4onnx]
- [x] NCHW and NHWC conversion [8. scc4onnx]
- [x] Add Node (no tested) [9. sna4onnx]
- [ ] Initialize Batchsize [10. sbi4onnx]

## References
- https://github.com/jchanvfx/NodeGraphQt
- https://github.com/PINTO0309/simple-onnx-processing-tools
- https://fdwr.github.io/LostOnnxDocs/OperatorFormulas.html
- https://github.com/onnx/onnx/blob/main/docs/Operators.md


